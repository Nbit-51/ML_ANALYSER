"""Approval-bound, alternating baseline/candidate benchmark protocol."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from ml_analyser.adapters.process import ProcessAdapter, ProcessManifest, ProcessOutput
from ml_analyser.agent.approval import ApprovalService
from ml_analyser.agent.evaluator import DecisionEvaluator
from ml_analyser.agent.ids import stable_id
from ml_analyser.agent.measurements import environment_fingerprint, summarize
from ml_analyser.agent.models import (
    AnalysisContext,
    ApprovalRecord,
    DecisionRecord,
    DecisionStatus,
    EvidenceKind,
    EvidenceRecord,
    ExperimentSpec,
    ExperimentStatus,
    Hypothesis,
    Measurement,
    ProjectStateGraph,
    RepositoryInventory,
    ResourceUsage,
    RiskLevel,
    RunState,
    StrictModel,
    SuccessContract,
)
from ml_analyser.agent.ports import ModelProvider, RepositoryInspector
from ml_analyser.agent.state_graph import InventoryStateGraphBuilder
from ml_analyser.execution.sandbox import SandboxError, sandbox_available
from ml_analyser.execution.workspace import IsolatedWorkspaceManager
from ml_analyser.persistence.sqlite import SQLiteRunStore


class ProcessPlan(StrictModel):
    run_id: str
    project_id: str
    project_path: str
    source_fingerprint: str
    success_contract: SuccessContract
    manifest: ProcessManifest
    hypothesis: Hypothesis
    experiment: ExperimentSpec


class ProcessPrepareResult(StrictModel):
    plan: ProcessPlan
    approval: ApprovalRecord
    inventory: RepositoryInventory
    state_graph: ProjectStateGraph
    evidence: list[EvidenceRecord]


class ProcessResult(StrictModel):
    run_id: str
    project_id: str
    final_state: RunState = RunState.COMPLETED
    state_history: list[RunState]
    approval: ApprovalRecord
    measurements: dict[str, list[Measurement]]
    evidence: list[EvidenceRecord]
    experiments: list[ExperimentSpec]
    decision: DecisionRecord
    disposition: str
    retained_candidate_workspace: str | None
    applied_changes: list[str]
    original_project_modified: bool = False


def source_fingerprint(inventory: RepositoryInventory) -> str:
    if inventory.skipped_paths or any(item.sha256 is None for item in inventory.files):
        raise SandboxError("execution requires a complete inventory with content hashes")
    return stable_id("snapshot", *(f"{f.path}:{f.sha256}" for f in inventory.files))


class ProcessPipeline:
    def __init__(
        self,
        *,
        provider: ModelProvider,
        inspector: RepositoryInspector,
        approvals: ApprovalService,
        evaluator: DecisionEvaluator,
        workspaces: IsolatedWorkspaceManager,
        store: SQLiteRunStore,
    ) -> None:
        self.provider = provider
        self.inspector = inspector
        self.approvals = approvals
        self.evaluator = evaluator
        self.workspaces = workspaces
        self.store = store
        self.adapter = ProcessAdapter()

    async def prepare(
        self,
        *,
        project_id: str,
        project_path: str,
        project_root: Path,
        success_contract: SuccessContract,
    ) -> ProcessPrepareResult:
        inventory = self.inspector.inspect(str(project_root))
        fingerprint = source_fingerprint(inventory)
        manifest = self.adapter.load_manifest(project_root)
        required = {
            success_contract.objective.metric,
            *(c.metric for c in success_contract.constraints),
        }
        if not required.issubset({m.name for m in manifest.metric_definitions}):
            raise SandboxError("contract metrics must be declared in the manifest")
        if success_contract.budget.max_cpu_seconds or success_contract.budget.max_gpu_seconds:
            raise SandboxError("aggregate CPU/GPU accounting is not implemented for this adapter")
        graph = InventoryStateGraphBuilder().build(project_id, inventory)
        run_id = str(uuid4())
        record = EvidenceRecord(
            id=stable_id("evidence", run_id, "declaration"),
            kind=EvidenceKind.CONFIGURATION,
            source="repo_benchmark.json",
            content_hash=fingerprint,
            claim="Declared benchmark protocol; not executed.",
            metadata={"manifest_json": manifest.model_dump_json()},
        )
        hypotheses = await self.provider.propose_hypotheses(
            AnalysisContext(
                project_id=project_id,
                success_contract=success_contract,
                inventory=inventory,
                state_graph=graph,
                evidence=[record],
            )
        )
        if not hypotheses or any(set(h.evidence_ids) - {record.id} for h in hypotheses):
            raise SandboxError("provider returned missing or unknown evidence references")
        hypothesis = next((h for h in hypotheses if h.kind == "optimization"), hypotheses[0])
        experiment = ExperimentSpec(
            id=stable_id("experiment", run_id, "candidate"),
            hypothesis_id=hypothesis.id,
            title=f"Declared {manifest.profile} comparison",
            change_summary=[
                f"Set {k} to {v!r}" for k, v in sorted(manifest.candidate_overrides.items())
            ],
            command=manifest.command,
            measurements=sorted(required),
            procedure=[
                "Create isolated copies; apply declared candidate config.",
                f"Warm up {manifest.warmup_count} rounds per variant.",
                f"Alternate order for {manifest.repetitions} paired measurement rounds.",
                "Require correctness equivalence; evaluate scalar means and reliability.",
            ],
            status=ExperimentStatus.AWAITING_APPROVAL,
        )
        plan = ProcessPlan(
            run_id=run_id,
            project_id=project_id,
            project_path=project_path,
            source_fingerprint=fingerprint,
            success_contract=success_contract,
            manifest=manifest,
            hypothesis=hypothesis,
            experiment=experiment,
        )
        approval = self.approvals.request(
            run_id=run_id,
            experiment_id=experiment.id,
            scope=plan,
            summary="Execute the declared sandboxed benchmark protocol.",
            risk_level=RiskLevel.HIGH,
        )
        self.store.append(run_id, record)
        return ProcessPrepareResult(
            plan=plan, approval=approval, inventory=inventory, state_graph=graph, evidence=[record]
        )

    def execute(
        self,
        *,
        plan: ProcessPlan,
        approval_id: str,
        project_root: Path,
        on_state: Callable[[RunState], None] | None = None,
    ) -> ProcessResult:
        if not sandbox_available():
            raise SandboxError(
                "sandbox unavailable; generic execution is preview only on this host"
            )
        if source_fingerprint(self.inspector.inspect(str(project_root))) != plan.source_fingerprint:
            raise SandboxError("project changed after preparation")
        approval = self.approvals.authorize(approval_id, plan)
        history = [RunState.AWAITING_APPROVAL, RunState.EXECUTING]
        if on_state:
            on_state(RunState.EXECUTING)
        handles = []
        retained = None
        observations: dict[str, list[ProcessOutput]] = {"baseline": [], "candidate": []}
        failed = {"baseline": 0, "candidate": 0}
        sample_ids: dict[str, list[str]] = {"baseline": [], "candidate": []}
        artifact_ids: dict[str, list[str]] = {"baseline": [], "candidate": []}
        started = perf_counter()
        try:
            for label in observations:
                handles.append(
                    self.workspaces.create(
                        run_id=plan.run_id, label=label, source_root=project_root
                    )
                )
            # Close the copy/approval race before any repository command starts.
            for handle in handles:
                if (
                    source_fingerprint(self.inspector.inspect(str(handle.workspace_root)))
                    != plan.source_fingerprint
                ):
                    raise SandboxError("copied workspace does not match approved source")
            changes = self.adapter.apply_candidate(handles[1].workspace_root, plan.manifest)
            fingerprint = environment_fingerprint()
            budget_seconds = plan.success_contract.budget.max_wall_clock_seconds
            for index in range(plan.manifest.warmup_count + plan.manifest.repetitions):
                warmup = index < plan.manifest.warmup_count
                order = handles if index % 2 == 0 else list(reversed(handles))
                for handle in order:
                    label = handle.label
                    observation = None
                    failure = None
                    try:
                        if budget_seconds and perf_counter() - started >= budget_seconds:
                            raise SandboxError("wall-clock budget exhausted")
                        observation = self.adapter.measure(handle.workspace_root, plan.manifest)
                    except (OSError, ValueError) as error:
                        failure = str(error)[:500]
                        failed[label] += 1
                    record = EvidenceRecord(
                        id=stable_id("sample", plan.run_id, label, str(index)),
                        kind=EvidenceKind.TOOL_OUTPUT,
                        source="generic_process",
                        claim=f"{label} {'warmup' if warmup else 'measurement'} round {index}: "
                        + ("failed" if failure else "executed"),
                        metadata={
                            "label": label,
                            "round": index,
                            "warmup": warmup,
                            "error": failure,
                            "environment_fingerprint": fingerprint,
                            "output_json": observation.model_dump_json() if observation else None,
                        },
                    )
                    if observation:
                        record.metadata["artifacts_json"] = json.dumps(
                            [
                                artifact.model_copy(
                                    update={"evidence_ids": [record.id]}
                                ).model_dump()
                                for artifact in observation.artifacts
                            ]
                        )
                        artifact_ids[label].extend(a.id for a in observation.artifacts)
                    self.store.append(plan.run_id, record)
                    if not warmup:
                        sample_ids[label].append(record.id)
                        if observation:
                            observations[label].append(observation)
            measurements: dict[str, list[Measurement]] = {"baseline": [], "candidate": []}
            for label, outputs in observations.items():
                for definition in plan.manifest.metric_definitions:
                    samples = [
                        next(m.value for m in o.metrics if m.name == definition.name)
                        for o in outputs
                    ]
                    if samples:
                        summary = summarize(samples)
                        measurements[label].append(
                            Measurement(
                                metric=definition.name,
                                label=definition.label,
                                unit=definition.unit,
                                direction=definition.direction,
                                value=summary.mean,
                                raw_samples=samples,
                                summary=summary,
                                warmup_count=plan.manifest.warmup_count,
                                failed_sample_count=failed[label],
                                environment_fingerprint=fingerprint,
                                evidence_ids=sample_ids[label],
                                artifact_ids=list(dict.fromkeys(artifact_ids[label])),
                            )
                        )
            decision = self.evaluator.evaluate(
                experiment_id=plan.experiment.id,
                contract=plan.success_contract,
                baseline=measurements["baseline"],
                candidate=measurements["candidate"],
                usage=ResourceUsage(wall_clock_seconds=perf_counter() - started),
            )
            signatures = {o.correctness for values in observations.values() for o in values}
            if len(signatures) > 1:
                decision = decision.model_copy(
                    update={
                        "status": DecisionStatus.REJECTED,
                        "reason": "Correctness regression or inconsistent baseline output.",
                    }
                )
            baseline = plan.experiment.model_copy(
                update={
                    "id": stable_id("experiment", plan.run_id, "baseline"),
                    "title": "Measured baseline",
                    "status": ExperimentStatus.MEASURED
                    if observations["baseline"]
                    else ExperimentStatus.FAILED,
                    "change_summary": ["No change"],
                }
            )
            candidate = plan.experiment.model_copy(
                update={
                    "parent_experiment_id": baseline.id,
                    "status": ExperimentStatus(decision.status.value),
                }
            )
            for experiment in (baseline, candidate):
                self.store.add_experiment(plan.run_id, experiment)
            if decision.status == DecisionStatus.ACCEPTED:
                retained = str(self.workspaces.retain(handles[1]))
            for state in (
                RunState.MEASURING,
                RunState.DECIDING,
                RunState.REPORTING,
                RunState.COMPLETED,
            ):
                history.append(state)
                if on_state:
                    on_state(state)
            return ProcessResult(
                run_id=plan.run_id,
                project_id=plan.project_id,
                state_history=history,
                approval=approval,
                measurements=measurements,
                evidence=self.store.list_for_run(plan.run_id),
                experiments=[baseline, candidate],
                decision=decision,
                applied_changes=changes,
                disposition="retained" if retained else "discarded",
                retained_candidate_workspace=retained,
            )
        finally:
            for handle in handles:
                if str(handle.workspace_root) != retained:
                    self.workspaces.discard(handle)
