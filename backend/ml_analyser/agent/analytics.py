"""Adapter-neutral API comparisons and reports from immutable persisted run snapshots."""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field

from ml_analyser.agent.ids import stable_id
from ml_analyser.agent.models import (
    ArtifactRecord,
    BenchmarkReliability,
    Capability,
    DecisionRecord,
    EvidenceKind,
    EvidenceRecord,
    ExperimentSpec,
    GraphEdgeType,
    GraphNodeType,
    Hypothesis,
    Measurement,
    MetricDirection,
    ProjectEdge,
    ProjectNode,
    ProjectStateGraph,
    RepositorySummary,
    ResourceUsage,
    StrictModel,
    SuccessContract,
)
from ml_analyser.persistence.sqlite import SQLiteRunStore


class MetricComparison(StrictModel):
    name: str
    label: str
    unit: str | None
    direction: MetricDirection | None
    baseline: float | None
    candidate: float | None
    delta: float | None
    percentage_delta: float | None
    status: str
    raw_samples_exist: bool
    evidence_ids: list[str]


class RunReport(StrictModel):
    repository: str
    objective_and_constraints: SuccessContract
    exact_change: list[str]
    methodology: list[str]
    command: list[str] | None
    configuration_json: str
    source_fingerprint: str
    decision: str
    disposition: str
    resource_usage: ResourceUsage
    evidence_ids: list[str]
    limitations: list[str]


class WorkbenchResult(StrictModel):
    run_id: str
    project_id: str
    adapter: str
    final_state: str
    state_history: list[str]
    success_contract: SuccessContract
    repository_summary: RepositorySummary
    hypothesis: Hypothesis
    measurements: dict[str, list[Measurement]]
    comparisons: list[MetricComparison]
    benchmark_reliability: BenchmarkReliability
    evidence: list[EvidenceRecord]
    experiments: list[ExperimentSpec]
    decision: DecisionRecord
    disposition: str
    retained_candidate_workspace: str | None
    applied_changes: list[str]
    original_project_modified: bool = False
    report: RunReport
    experiment_graph: ProjectStateGraph
    artifacts: list[ArtifactRecord] = Field(default_factory=list)


def experiment_graph(
    project_id: str, experiments: list[ExperimentSpec], measurements: dict[str, list[Measurement]]
) -> ProjectStateGraph:
    root_id = stable_id("repository", project_id)
    nodes = [ProjectNode(id=root_id, type=GraphNodeType.PROJECT, label=project_id)]
    edges = []
    for experiment in experiments:
        nodes.append(
            ProjectNode(
                id=experiment.id,
                type=GraphNodeType.EXPERIMENT,
                label=experiment.title,
                metadata={"status": experiment.status.value},
            )
        )
        edges.append(
            ProjectEdge(
                source_id=root_id,
                target_id=experiment.id,
                type=GraphEdgeType.CONTAINS,
                provenance="measured",
            )
        )
        if experiment.parent_experiment_id:
            edges.append(
                ProjectEdge(
                    source_id=experiment.id,
                    target_id=experiment.parent_experiment_id,
                    type=GraphEdgeType.DEPENDS_ON,
                    provenance="declared",
                )
            )
        variant = "candidate" if experiment.parent_experiment_id else "baseline"
        for measurement in measurements[variant]:
            node_id = stable_id("measurement", experiment.id, measurement.metric)
            nodes.append(
                ProjectNode(
                    id=node_id,
                    type=GraphNodeType.MEASUREMENT,
                    label=measurement.metric,
                    metadata={"value": measurement.value, "unit": measurement.unit},
                )
            )
            edges.append(
                ProjectEdge(
                    source_id=experiment.id,
                    target_id=node_id,
                    type=GraphEdgeType.MEASURES,
                    provenance="measured",
                    evidence_ids=measurement.evidence_ids,
                )
            )
    return ProjectStateGraph(project_id=project_id, nodes=nodes, edges=edges)


def comparisons(
    measurements: dict[str, list[Measurement]], contract: SuccessContract, decision: DecisionRecord
) -> list[MetricComparison]:
    baseline = {m.metric: m for m in measurements["baseline"]}
    candidate = {m.metric: m for m in measurements["candidate"]}
    results = []
    for name in sorted(baseline.keys() | candidate.keys()):
        a, b = baseline.get(name), candidate.get(name)
        metadata = b or a
        assert metadata is not None
        comparable = a is not None and b is not None and a.unit == b.unit
        delta = b.value - a.value if comparable and a and b else None
        direction = (
            contract.objective.direction
            if name == contract.objective.metric
            else metadata.direction
        )
        status = "informational"
        if name == contract.objective.metric:
            status = (
                "inconclusive"
                if not decision.objective
                else "pass"
                if decision.objective.passed
                else "fail"
            )
        for constraint in decision.constraints:
            if constraint.metric == name:
                status = "pass" if constraint.passed else "fail"
        results.append(
            MetricComparison(
                name=name,
                label=metadata.label or name.replace("_", " "),
                unit=metadata.unit,
                direction=direction,
                baseline=a.value if a else None,
                candidate=b.value if b else None,
                delta=delta,
                percentage_delta=delta / abs(a.value) * 100
                if delta is not None and a and a.value
                else None,
                status=status,
                raw_samples_exist=bool((a and a.raw_samples) or (b and b.raw_samples)),
                evidence_ids=list(
                    dict.fromkeys([*(a.evidence_ids if a else []), *(b.evidence_ids if b else [])])
                ),
            )
        )
    return results


def ml_measurements(result: Any, plan: Any) -> dict[str, list[Measurement]]:
    definitions = {m.name: m for m in plan.manifest.metric_definitions}
    return {
        label: [
            Measurement(
                metric=name,
                value=value,
                unit=definitions[name].unit,
                label=definitions[name].label,
                direction=definitions[name].direction,
                evidence_ids=[result.evidence[index].id],
            )
            for name, value in getattr(result, label).metrics.items()
        ]
        for index, label in enumerate(("baseline", "candidate"))
    }


def http_measurements(result: Any, plan: Any) -> dict[str, list[Measurement]]:
    from ml_analyser.agent.backend_benchmark import BackendBenchmarkPipeline

    return {
        label: BackendBenchmarkPipeline._measurements(
            getattr(result, label),
            evidence_id=result.evidence[index].id,
            response_matches=float(
                label == "baseline"
                or (
                    result.baseline.response_hash not in {None, "inconsistent"}
                    and result.baseline.response_hash == result.candidate.response_hash
                )
            ),
        )
        for index, label in enumerate(("baseline", "candidate"))
    }


def persist_workbench_result(
    store: SQLiteRunStore,
    adapter: str,
    result: Any,
    plan: Any,
    measurements: dict[str, list[Measurement]],
    summary: RepositorySummary,
) -> WorkbenchResult:
    persisted = store.list_for_run(plan.run_id)
    artifacts: dict[str, ArtifactRecord] = {}
    for record in persisted:
        payload = record.metadata.get("artifacts_json")
        if isinstance(payload, str):
            for item in json.loads(payload):
                artifact = ArtifactRecord.model_validate(item)
                previous = artifacts.get(artifact.id)
                if previous:
                    artifact.evidence_ids = list(
                        dict.fromkeys([*previous.evidence_ids, *artifact.evidence_ids])
                    )
                artifacts[artifact.id] = artifact
    summary.capabilities.append(
        Capability(
            id=stable_id("capability", plan.run_id, "declared"),
            name="Approved benchmark profile",
            kind="benchmark_profile",
            provenance="declared",
            confidence=1,
            evidence_ids=[persisted[0].id],
            paths=[plan.project_path],
        )
    )
    measured_ids = list(
        dict.fromkeys(
            evidence_id
            for variant in measurements.values()
            for measurement in variant
            for evidence_id in measurement.evidence_ids
        )
    )
    if measured_ids:
        summary.capabilities.append(
            Capability(
                id=stable_id("capability", plan.run_id, "measured"),
                name="Observed benchmark outputs",
                kind="measurements",
                provenance="measured",
                confidence=1,
                evidence_ids=measured_ids,
                paths=[plan.project_path],
            )
        )
    report = RunReport(
        repository=plan.project_path,
        objective_and_constraints=plan.success_contract,
        exact_change=result.applied_changes,
        methodology=plan.experiment.procedure,
        command=plan.experiment.command,
        configuration_json=plan.manifest.model_dump_json(),
        source_fingerprint=plan.source_fingerprint,
        decision=result.decision.reason,
        disposition=result.disposition,
        resource_usage=result.decision.budget.usage,
        evidence_ids=[e.id for e in store.list_for_run(plan.run_id)],
        limitations=[
            "No statistical significance test was performed.",
            "Measurements describe this workload on this host; no universal speed claim.",
            "CPU, GPU and monetary usage are not instrumented by local adapters.",
        ],
    )
    normalized = WorkbenchResult(
        run_id=result.run_id,
        project_id=result.project_id,
        adapter=adapter,
        final_state=result.final_state,
        state_history=result.state_history,
        success_contract=plan.success_contract,
        repository_summary=summary,
        hypothesis=plan.hypothesis,
        measurements=measurements,
        comparisons=comparisons(measurements, plan.success_contract, result.decision),
        benchmark_reliability=result.decision.benchmark_reliability,
        evidence=store.list_for_run(plan.run_id),
        experiments=store.list_experiments(plan.run_id),
        decision=result.decision,
        disposition=result.disposition,
        retained_candidate_workspace=result.retained_candidate_workspace,
        applied_changes=result.applied_changes,
        experiment_graph=experiment_graph(
            result.project_id, store.list_experiments(plan.run_id), measurements
        ),
        report=report,
        artifacts=list(artifacts.values()),
    )
    store.append(
        plan.run_id,
        EvidenceRecord(
            id=stable_id("evidence", plan.run_id, "report"),
            kind=EvidenceKind.MEASUREMENT,
            claim="Persisted measured run and deterministic report.",
            source=adapter,
            metadata={"workbench_json": normalized.model_dump_json()},
        ),
    )
    # Return the serialized snapshot, so the report path never depends on provider memory.
    return read_report(store, plan.run_id)


def read_report(store: SQLiteRunStore, run_id: str) -> WorkbenchResult:
    for record in store.list_for_run(run_id):
        payload = record.metadata.get("workbench_json")
        if isinstance(payload, str):
            return WorkbenchResult.model_validate(json.loads(payload))
    raise ValueError("run report not found")
