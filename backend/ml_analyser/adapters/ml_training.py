"""Bounded Python training adapter for a manifest-declared ML project."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from pydantic import Field, field_validator

from ml_analyser.adapters.process import unique_json
from ml_analyser.agent.models import MetadataValue, MetricDefinition, StrictModel

MANIFEST_NAME = "ml_experiment.json"
SUPPORTED_METRICS = frozenset({"accuracy", "f1", "precision", "recall"})


class MlTrainingError(ValueError):
    """Raised when the declared training procedure cannot produce valid metrics."""


class MlTrainingManifest(StrictModel):
    adapter: str
    entrypoint: str
    config_file: str
    candidate_overrides: dict[str, MetadataValue]
    metrics_file: str = "metrics.json"
    timeout_seconds: int = Field(default=20, ge=1, le=120)
    metric_definitions: list[MetricDefinition] = Field(
        default_factory=lambda: [
            MetricDefinition(name=name, unit="ratio", minimum=0, maximum=1)
            for name in sorted(SUPPORTED_METRICS)
        ]
    )

    @field_validator("metric_definitions")
    @classmethod
    def unique_metrics(cls, value: list[MetricDefinition]) -> list[MetricDefinition]:
        if not value or len({m.name for m in value}) != len(value):
            raise ValueError("metric definitions must be nonempty and unique")
        return value

    @field_validator("adapter")
    @classmethod
    def require_adapter(cls, value: str) -> str:
        if value != "ml_training":
            raise ValueError("adapter must be 'ml_training'")
        return value


class MlTrainingObservation(StrictModel):
    metrics: dict[str, float]
    sample_count: int = Field(ge=1)
    duration_seconds: float = Field(ge=0)
    stdout_tail: str = ""
    stderr_tail: str = ""


class MlTrainingAdapter:
    """Run one declared script in a copied project, with no shell or inherited secrets."""

    name = "ml_training"
    supported_metrics = SUPPORTED_METRICS

    def load_manifest(self, project_root: Path) -> MlTrainingManifest:
        root = project_root.resolve(strict=True)
        if (root / MANIFEST_NAME).is_symlink():
            raise MlTrainingError("manifest symlinks are not permitted")
        try:
            manifest = MlTrainingManifest.model_validate_json(
                (root / MANIFEST_NAME).read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as error:
            raise MlTrainingError(f"invalid {MANIFEST_NAME}: {error}") from error
        self._resolve_file(root, manifest.entrypoint)
        self._resolve_file(root, manifest.config_file)
        self._metrics_path(root, manifest.metrics_file)
        if not manifest.candidate_overrides:
            raise MlTrainingError("candidate_overrides must contain a change")
        return manifest

    def apply_candidate(self, project_root: Path, manifest: MlTrainingManifest) -> list[str]:
        config_path = self._resolve_file(project_root.resolve(strict=True), manifest.config_file)
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise MlTrainingError(f"invalid training config: {error}") from error
        if not isinstance(config, dict):
            raise MlTrainingError("training config must be a JSON object")
        if not set(manifest.candidate_overrides).issubset(config):
            raise MlTrainingError("candidate overrides must refer to existing config keys")
        changes = []
        for key, value in sorted(manifest.candidate_overrides.items()):
            changes.append(f"{key}: {config[key]!r} -> {value!r}")
            config[key] = value
        config_path.write_text(
            json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return changes

    def measure(self, project_root: Path, manifest: MlTrainingManifest) -> MlTrainingObservation:
        root = project_root.resolve(strict=True)
        script = self._resolve_file(root, manifest.entrypoint)
        config = self._resolve_file(root, manifest.config_file)
        metrics_path = self._metrics_path(root, manifest.metrics_file)
        metrics_path.unlink(missing_ok=True)
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"PATH", "SYSTEMROOT", "TEMP", "TMP", "WINDIR"}
        }
        environment["PYTHONUNBUFFERED"] = "1"
        try:
            completed = subprocess.run(  # noqa: S603 - fixed interpreter and manifest checked paths
                [
                    sys.executable,
                    "-I",
                    str(script),
                    "--config",
                    str(config),
                    "--output",
                    str(metrics_path),
                ],
                cwd=root,
                env=environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=manifest.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise MlTrainingError(f"training process failed: {error}") from error
        if completed.returncode != 0:
            raise MlTrainingError(
                f"training exited with code {completed.returncode}: {completed.stderr[-1000:]}"
            )
        try:
            if metrics_path.stat().st_size > 65536:
                raise MlTrainingError("metric output exceeds 65536 bytes")
            payload = json.loads(
                metrics_path.read_text(encoding="utf-8"), object_pairs_hook=unique_json
            )
            observation = MlTrainingObservation.model_validate(payload)
        except (OSError, ValueError) as error:
            raise MlTrainingError(f"training did not produce valid metrics: {error}") from error
        if set(observation.metrics) != {m.name for m in manifest.metric_definitions}:
            raise MlTrainingError("training metrics must match declared metric definitions")
        for definition in manifest.metric_definitions:
            value = observation.metrics[definition.name]
            if (definition.minimum is not None and value < definition.minimum) or (
                definition.maximum is not None and value > definition.maximum
            ):
                raise MlTrainingError(f"metric outside declared bounds: {definition.name}")
        return observation.model_copy(
            update={
                "stdout_tail": completed.stdout[-2000:],
                "stderr_tail": completed.stderr[-2000:],
            }
        )

    @staticmethod
    def _resolve_file(root: Path, relative_path: str) -> Path:
        try:
            path = (root / relative_path).resolve(strict=True)
        except OSError as error:
            raise MlTrainingError(f"cannot resolve declared input file: {error}") from error
        if not path.is_relative_to(root) or not path.is_file():
            raise MlTrainingError("declared input file must stay inside the project")
        return path

    @staticmethod
    def _metrics_path(root: Path, relative_path: str) -> Path:
        path = (root / relative_path).resolve()
        if not path.is_relative_to(root) or path == root or path.parent != root:
            raise MlTrainingError("metrics_file must be a root-level project file")
        return path
