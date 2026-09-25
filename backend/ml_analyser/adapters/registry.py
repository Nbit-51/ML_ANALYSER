"""Adapter metadata and pipeline factories; route dispatch does not grow branches."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ml_analyser.agent.models import AdapterReadiness, Measurement
from ml_analyser.tools.repository import RepositoryInventoryTool


@dataclass(frozen=True)
class AdapterRegistration:
    name: str
    manifest_name: str
    profiles: tuple[str, ...]
    requirements: str
    pipeline: Callable[..., Any]
    plan_model: type[BaseModel]
    load_manifest: Callable[[Path], BaseModel]
    normalize: Callable[[Any, Any], dict[str, list[Measurement]]]
    available: Callable[[], bool] = lambda: True
    languages: tuple[str, ...] = ()
    supported_metrics: tuple[str, ...] = ()


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, AdapterRegistration] = {}

    def register(self, adapter: AdapterRegistration) -> None:
        if adapter.name in self._adapters:
            raise ValueError(f"adapter already registered: {adapter.name}")
        self._adapters[adapter.name] = adapter

    def get(self, name: str) -> AdapterRegistration:
        if name not in self._adapters:
            raise ValueError(f"unsupported adapter: {name}")
        return self._adapters[name]

    def describe(self, root: Path) -> list[AdapterReadiness]:
        readiness = []
        languages = {item.language for item in RepositoryInventoryTool().inspect(str(root)).files}
        for entry in self._adapters.values():
            status = "detected_but_needs_configuration"
            reason = f"Requires {entry.manifest_name}. {entry.requirements}"
            metrics = list(entry.supported_metrics)
            if entry.languages and not languages.intersection(entry.languages):
                status = "unsupported"
                reason = "No compatible source language detected. " + reason
            if (root / entry.manifest_name).is_file():
                try:
                    manifest = entry.load_manifest(root)
                    if hasattr(manifest, "metric_definitions"):
                        metrics = [definition.name for definition in manifest.metric_definitions]
                    status = "supported_and_executable" if entry.available() else "preview_only"
                    reason = entry.requirements + "; explicit approval required"
                except ValueError as error:
                    status = "detected_but_needs_configuration"
                    reason = str(error)
            readiness.append(
                AdapterReadiness(
                    adapter=entry.name,
                    status=status,
                    reason=reason,
                    profiles=list(entry.profiles),
                    required_configuration=entry.manifest_name,
                    supported_measurements=metrics,
                )
            )
        return readiness


def default_registry() -> AdapterRegistry:
    from ml_analyser.adapters.backend_http import BackendHttpBenchmarkAdapter
    from ml_analyser.adapters.ml_training import MlTrainingAdapter
    from ml_analyser.adapters.process import ProcessAdapter
    from ml_analyser.agent.analytics import http_measurements, ml_measurements
    from ml_analyser.agent.backend_benchmark import BackendBenchmarkPipeline, BackendBenchmarkPlan
    from ml_analyser.agent.ml_training import MlTrainingPipeline, MlTrainingPlan
    from ml_analyser.agent.process_benchmark import ProcessPipeline, ProcessPlan
    from ml_analyser.execution.sandbox import sandbox_available

    registry = AdapterRegistry()
    registry.register(
        AdapterRegistration(
            "ml_training",
            "ml_experiment.json",
            ("training",),
            "Trusted local Python training demo; workspace isolation only",
            MlTrainingPipeline,
            MlTrainingPlan,
            MlTrainingAdapter().load_manifest,
            ml_measurements,
            languages=("python",),
        )
    )
    registry.register(
        AdapterRegistration(
            "backend_http",
            "backend_benchmark.json",
            ("http",),
            "Trusted localhost Python backend demo; workspace isolation only",
            BackendBenchmarkPipeline,
            BackendBenchmarkPlan,
            BackendHttpBenchmarkAdapter().load_manifest,
            http_measurements,
            languages=("python",),
            supported_metrics=tuple(sorted(BackendHttpBenchmarkAdapter.supported_metrics)),
        )
    )
    registry.register(
        AdapterRegistration(
            "generic_process",
            "repo_benchmark.json",
            ("cli", "test_suite", "build", "microbenchmark"),
            "Linux bubblewrap with network namespace isolation required",
            ProcessPipeline,
            ProcessPlan,
            ProcessAdapter().load_manifest,
            lambda result, plan: result.measurements,
            sandbox_available,
        )
    )
    return registry
