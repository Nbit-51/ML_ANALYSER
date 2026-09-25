"""Controlled localhost HTTP benchmark adapter for Python backend projects."""

from __future__ import annotations

import json
import math
import os
import socket
import subprocess
import sys
import time
from hashlib import sha256
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from pydantic import Field, field_validator

from ml_analyser.agent.measurements import environment_fingerprint
from ml_analyser.agent.models import MetadataValue, StrictModel

MANIFEST_NAME = "backend_benchmark.json"
MAX_CAPTURED_LOG_CHARACTERS = 2_000


class BackendAdapterError(ValueError):
    """Raised when a backend benchmark cannot be prepared or measured safely."""


class BackendBenchmarkManifest(StrictModel):
    adapter: str
    entrypoint: str
    config_file: str
    candidate_overrides: dict[str, MetadataValue]
    health_path: str = "/health"
    benchmark_path: str = "/benchmark"
    requests: int = Field(default=25, ge=5, le=500)
    warmup_requests: int = Field(default=3, ge=0, le=100)
    repetitions: int = Field(default=3, ge=1, le=10)
    startup_timeout_seconds: float = Field(default=5.0, gt=0.0, le=30.0)
    request_timeout_seconds: float = Field(default=2.0, gt=0.0, le=10.0)

    @field_validator("adapter")
    @classmethod
    def adapter_must_match(cls, adapter: str) -> str:
        if adapter != "backend_http":
            raise ValueError("adapter must be 'backend_http'")
        return adapter

    @field_validator("health_path", "benchmark_path")
    @classmethod
    def path_must_be_local_absolute(cls, path: str) -> str:
        if not path.startswith("/") or "://" in path:
            raise ValueError("HTTP paths must begin with '/' and cannot contain a URL scheme")
        return path


class BackendObservation(StrictModel):
    requests: int = Field(ge=1)
    successful_requests: int = Field(ge=0)
    error_count: int = Field(ge=0)
    error_rate: float = Field(ge=0.0, le=1.0)
    p50_latency_ms: float = Field(ge=0.0)
    p95_latency_ms: float = Field(ge=0.0)
    mean_latency_ms: float = Field(ge=0.0)
    throughput_requests_per_second: float = Field(ge=0.0)
    response_hash: str | None
    stdout_tail: str = ""
    stderr_tail: str = ""
    raw_latency_samples: list[float] = Field(default_factory=list)
    p99_latency_ms: float = 0
    warmup_count: int = 0
    repetitions: int = 1
    latency_rounds: list[list[float]] = Field(default_factory=list)
    environment_fingerprint: str | None = None
    response_bytes: int = 0


class BackendHttpBenchmarkAdapter:
    """Benchmark one localhost endpoint from an isolated Python project copy."""

    name = "backend_http"
    supported_metrics = frozenset(
        {
            "error_rate",
            "mean_latency_ms",
            "p50_latency_ms",
            "p95_latency_ms",
            "p99_latency_ms",
            "successful_requests",
            "response_bytes",
            "response_hash_matches",
            "throughput_requests_per_second",
        }
    )

    def load_manifest(self, project_root: Path) -> BackendBenchmarkManifest:
        root = project_root.resolve(strict=True)
        manifest_path = root / MANIFEST_NAME
        if manifest_path.is_symlink():
            raise BackendAdapterError("manifest symlinks are not permitted")
        if not manifest_path.is_file():
            raise BackendAdapterError(f"missing required manifest: {MANIFEST_NAME}")
        try:
            manifest = BackendBenchmarkManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as error:
            raise BackendAdapterError(f"invalid {MANIFEST_NAME}: {error}") from error

        self._resolve_project_file(root, manifest.entrypoint, "entrypoint")
        self._resolve_project_file(root, manifest.config_file, "config_file")
        return manifest

    def apply_candidate(self, project_root: Path, manifest: BackendBenchmarkManifest) -> list[str]:
        root = project_root.resolve(strict=True)
        config_path = self._resolve_project_file(root, manifest.config_file, "config_file")
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise BackendAdapterError(f"invalid JSON config: {error}") from error
        if not isinstance(config, dict):
            raise BackendAdapterError("backend config must be a JSON object")

        changes: list[str] = []
        for key, value in sorted(manifest.candidate_overrides.items()):
            previous = config.get(key)
            config[key] = value
            changes.append(f"{key}: {previous!r} -> {value!r}")
        config_path.write_text(
            json.dumps(config, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return changes

    def measure(self, project_root: Path, manifest: BackendBenchmarkManifest) -> BackendObservation:
        root = project_root.resolve(strict=True)
        entrypoint = self._resolve_project_file(root, manifest.entrypoint, "entrypoint")
        port = self._reserve_local_port()
        environment = self._subprocess_environment()
        process = subprocess.Popen(  # noqa: S603 - absolute interpreter, no shell, approved scope
            [sys.executable, "-I", str(entrypoint), "--port", str(port)],
            cwd=root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        stdout = ""
        stderr = ""
        try:
            self._wait_until_healthy(process, port, manifest)
            latencies: list[float] = []
            response_hashes: list[str] = []
            errors = 0
            response_bytes = 0
            for _ in range(manifest.warmup_requests):
                try:
                    with urlopen(
                        f"http://127.0.0.1:{port}{manifest.benchmark_path}",
                        timeout=manifest.request_timeout_seconds,
                    ) as response:
                        response.read(1048577)
                except (OSError, URLError):
                    pass
            benchmark_started = time.perf_counter()
            for _ in range(manifest.requests * manifest.repetitions):
                started = time.perf_counter()
                try:
                    with urlopen(  # noqa: S310 - fixed localhost URL generated below
                        f"http://127.0.0.1:{port}{manifest.benchmark_path}",
                        timeout=manifest.request_timeout_seconds,
                    ) as response:
                        body = response.read(1048577)
                        if response.status != 200 or len(body) > 1048576:
                            errors += 1
                            continue
                        response_hashes.append(sha256(body).hexdigest())
                        response_bytes += len(body)
                except (OSError, URLError):
                    errors += 1
                    continue
                latencies.append((time.perf_counter() - started) * 1_000)
            elapsed = time.perf_counter() - benchmark_started
        finally:
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=3)

        total_requests = manifest.requests * manifest.repetitions
        successful = total_requests - errors
        if successful == 0 or not response_hashes:
            raise BackendAdapterError(
                "all benchmark requests failed; "
                f"stderr={self._tail(stderr)!r}, stdout={self._tail(stdout)!r}"
            )
        ordered = sorted(latencies)
        return BackendObservation(
            requests=total_requests,
            successful_requests=successful,
            error_count=errors,
            error_rate=errors / total_requests,
            p50_latency_ms=self._percentile(ordered, 0.50),
            p95_latency_ms=self._percentile(ordered, 0.95),
            mean_latency_ms=sum(ordered) / len(ordered),
            throughput_requests_per_second=successful / elapsed if elapsed else 0.0,
            response_hash=(
                response_hashes[0] if len(set(response_hashes)) == 1 else "inconsistent"
            ),
            stdout_tail=self._tail(stdout),
            stderr_tail=self._tail(stderr),
            raw_latency_samples=latencies,
            p99_latency_ms=self._percentile(ordered, 0.99),
            warmup_count=manifest.warmup_requests,
            repetitions=manifest.repetitions,
            latency_rounds=[
                latencies[i : i + manifest.requests]
                for i in range(0, len(latencies), manifest.requests)
            ],
            environment_fingerprint=environment_fingerprint(),
            response_bytes=response_bytes,
        )

    @staticmethod
    def _resolve_project_file(root: Path, configured_path: str, field: str) -> Path:
        try:
            path = (root / configured_path).resolve(strict=True)
        except OSError as error:
            raise BackendAdapterError(f"cannot resolve {field}: {error}") from error
        try:
            path.relative_to(root)
        except ValueError as error:
            raise BackendAdapterError(f"{field} must stay inside the project directory") from error
        if not path.is_file():
            raise BackendAdapterError(f"{field} must identify a file")
        return path

    @staticmethod
    def _reserve_local_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as local_socket:
            local_socket.bind(("127.0.0.1", 0))
            return int(local_socket.getsockname()[1])

    @staticmethod
    def _subprocess_environment() -> dict[str, str]:
        allowed = {"PATH", "SYSTEMROOT", "TEMP", "TMP", "WINDIR"}
        environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
        environment["PYTHONUNBUFFERED"] = "1"
        return environment

    @staticmethod
    def _wait_until_healthy(
        process: subprocess.Popen[str],
        port: int,
        manifest: BackendBenchmarkManifest,
    ) -> None:
        deadline = time.monotonic() + manifest.startup_timeout_seconds
        url = f"http://127.0.0.1:{port}{manifest.health_path}"
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise BackendAdapterError(
                    f"backend process exited during startup with code {process.returncode}"
                )
            try:
                with urlopen(url, timeout=0.25) as response:  # noqa: S310 - localhost only
                    if response.status == 200:
                        return
            except (OSError, URLError):
                time.sleep(0.025)
        raise BackendAdapterError("backend did not become healthy before the startup timeout")

    @staticmethod
    def _percentile(ordered_values: list[float], percentile: float) -> float:
        index = max(0, math.ceil(percentile * len(ordered_values)) - 1)
        return ordered_values[index]

    @staticmethod
    def _tail(output: str) -> str:
        return output[-MAX_CAPTURED_LOG_CHARACTERS:]
