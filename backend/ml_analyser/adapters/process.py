"""Declared CLI, test, build and microbenchmark harness adapter."""

from __future__ import annotations

import base64
import json
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Literal

from pydantic import Field, model_validator

from ml_analyser.agent.ids import stable_id
from ml_analyser.agent.models import ArtifactRecord, MetadataValue, MetricDefinition, StrictModel
from ml_analyser.execution.sandbox import ResourceLimits, SandboxError, run_sandbox, safe_path

EXECUTABLES = frozenset(
    {
        "/usr/bin/python3",
        "/usr/bin/node",
        "/usr/bin/make",
        "/usr/bin/cmake",
        "/usr/bin/gcc",
        "/usr/bin/g++",
        "/usr/bin/go",
        "/usr/bin/cargo",
        "/usr/bin/java",
    }
)


class ProcessManifest(StrictModel):
    adapter: Literal["generic_process"] = "generic_process"
    profile: Literal["cli", "test_suite", "build", "microbenchmark"]
    working_directory: str = "."
    command: list[str] = Field(min_length=1, max_length=64)
    build_command: list[str] | None = None
    test_command: list[str] | None = None
    config_file: str
    candidate_overrides: dict[str, MetadataValue]
    metric_definitions: list[MetricDefinition] = Field(min_length=1, max_length=64)
    metrics_file: str | None = None
    warmup_count: int = Field(default=1, ge=0, le=10)
    repetitions: int = Field(default=5, ge=1, le=50)
    environment: dict[str, str] = Field(default_factory=dict)
    allowed_output_paths: list[str] = Field(default_factory=list, max_length=16)
    network: Literal["denied"] = "denied"
    limits: ResourceLimits = Field(default_factory=ResourceLimits)
    correctness_required: Literal[True] = True

    @model_validator(mode="after")
    def validate_declaration(self) -> ProcessManifest:
        if len({m.name for m in self.metric_definitions}) != len(self.metric_definitions):
            raise ValueError("duplicate metric definition")
        for command in (self.command, self.build_command, self.test_command):
            if command is not None and (not command or command[0] not in EXECUTABLES):
                raise ValueError(
                    "undeclared executable; command must use an allowed absolute runtime"
                )
            if command and any("\x00" in part or len(part) > 1000 for part in command):
                raise ValueError("invalid command argument")
        if set(self.environment) - {"LANG", "LC_ALL", "OMP_NUM_THREADS"}:
            raise ValueError("environment keys are outside the allowlist")
        if self.metrics_file is not None and self.metrics_file not in self.allowed_output_paths:
            raise ValueError("metric output must be an allowed output path")
        if len(set(self.allowed_output_paths)) != len(self.allowed_output_paths):
            raise ValueError("duplicate output path")
        if not self.candidate_overrides:
            raise ValueError("candidate requires a declared change")
        return self


class MetricOutput(StrictModel):
    name: str
    value: float = Field(strict=True)
    unit: str | None = None


class ProcessOutput(StrictModel):
    metrics: list[MetricOutput]
    correctness: str = Field(min_length=1, max_length=1000)


class ProcessObservation(ProcessOutput):
    artifacts: list[ArtifactRecord] = Field(default_factory=list)


def unique_json(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


class ProcessAdapter:
    name = "generic_process"

    def load_manifest(self, project_root: Path) -> ProcessManifest:
        root = project_root.resolve(strict=True)
        try:
            manifest_path = safe_path(root, "repo_benchmark.json")
            if manifest_path.stat().st_size > 65536:
                raise ValueError("manifest too large")
            manifest = ProcessManifest.model_validate(
                json.loads(manifest_path.read_text(encoding="utf-8"), object_pairs_hook=unique_json)
            )
            if not safe_path(root, manifest.working_directory).is_dir():
                raise ValueError("working_directory must be a directory")
            if not safe_path(root, manifest.config_file).is_file():
                raise ValueError("config_file must be a file")
            for path in manifest.allowed_output_paths:
                target = safe_path(root, path, exists=False)
                if target.exists():
                    raise ValueError("output must not overwrite repository inputs")
            return manifest
        except (OSError, ValueError) as error:
            raise SandboxError(f"invalid repo_benchmark.json: {error}") from error

    def apply_candidate(self, root: Path, manifest: ProcessManifest) -> list[str]:
        path = safe_path(root, manifest.config_file)
        config = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_json)
        if not isinstance(config, dict) or not set(manifest.candidate_overrides).issubset(config):
            raise SandboxError("candidate overrides require existing JSON config keys")
        changes = [
            f"{key}: {config[key]!r} -> {value!r}"
            for key, value in sorted(manifest.candidate_overrides.items())
        ]
        config.update(manifest.candidate_overrides)
        path.write_text(json.dumps(config, sort_keys=True), encoding="utf-8")
        return changes

    def measure(self, root: Path, manifest: ProcessManifest) -> ProcessObservation:
        started = perf_counter()
        # A missing emission must never reuse metrics from an earlier repetition.
        if manifest.metrics_file:
            safe_path(root, manifest.metrics_file, exists=False).unlink(missing_ok=True)
        environment = {
            "PATH": "/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
            **manifest.environment,
        }
        text = ""
        for command in (manifest.build_command, manifest.test_command, manifest.command):
            if command is not None:
                if command == manifest.command and manifest.metrics_file:
                    safe_path(root, manifest.metrics_file, exists=False).unlink(missing_ok=True)
                text = run_sandbox(
                    root,
                    command,
                    manifest.working_directory,
                    manifest.allowed_output_paths,
                    environment,
                    manifest.limits,
                )
        if manifest.metrics_file:
            path = safe_path(root, manifest.metrics_file)
            if path.stat().st_size > manifest.limits.output_bytes:
                raise SandboxError("metric output limit exceeded")
            text = path.read_text(encoding="utf-8")
        try:
            observation = ProcessOutput.model_validate(
                json.loads(text, object_pairs_hook=unique_json)
            )
        except ValueError as error:
            raise SandboxError(f"malformed metric output: {error}") from error
        values = {m.name: m for m in observation.metrics}
        if len(values) != len(observation.metrics):
            raise SandboxError("duplicate metric")
        if "process_duration_ms" in values:
            raise SandboxError("process_duration_ms is reserved for the measured tool duration")
        if any(m.name == "process_duration_ms" for m in manifest.metric_definitions):
            duration = MetricOutput(
                name="process_duration_ms", unit="ms", value=(perf_counter() - started) * 1000
            )
            observation.metrics.append(duration)
            values[duration.name] = duration
        if set(values) != {m.name for m in manifest.metric_definitions}:
            raise SandboxError("missing or undeclared metric")
        for definition in manifest.metric_definitions:
            metric = values[definition.name]
            if metric.unit != definition.unit:
                raise SandboxError("wrong metric unit")
            if (definition.minimum is not None and metric.value < definition.minimum) or (
                definition.maximum is not None and metric.value > definition.maximum
            ):
                raise SandboxError("metric outside declared bounds")
        artifacts = []
        total_bytes = 0
        for relative in manifest.allowed_output_paths:
            path = safe_path(root, relative)
            with path.open("rb") as handle:
                contents = handle.read(manifest.limits.output_bytes + 1)
            total_bytes += len(contents)
            if total_bytes > manifest.limits.output_bytes:
                raise SandboxError("combined artifact output limit exceeded")
            digest = sha256(contents).hexdigest()
            artifacts.append(
                ArtifactRecord(
                    id=stable_id("artifact", relative, digest),
                    path=relative,
                    sha256=digest,
                    size_bytes=len(contents),
                    content_base64=base64.b64encode(contents).decode("ascii"),
                )
            )
        return ProcessObservation(**observation.model_dump(), artifacts=artifacts)
