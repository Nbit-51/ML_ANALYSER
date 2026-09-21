"""Approval-gated backend benchmark preparation and execution pipeline."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Literal
from uuid import uuid4

from pydantic import Field

from ml_analyser.adapters.backend_http import (
    BackendAdapterError,
    BackendBenchmarkManifest,
    BackendHttpBenchmarkAdapter,
    BackendObservation,
)
from ml_analyser.agent.approval import ApprovalService
from ml_analyser.agent.evaluator import DecisionEvaluator
from ml_analyser.agent.ids import stable_id
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
    HypothesisKind,
    Measurement,
    MetricDirection,
    ProjectStateGraph,
    RepositoryInventory,
    ResourceUsage,
    RiskLevel,
    RunState,
    StrictModel,
    SuccessContract,
)
from ml_analyser.agent.ports import ModelProvider, RepositoryInspector
from ml_analyser.agent.state import RunLifecycle
from ml_analyser.agent.state_graph import InventoryStateGraphBuilder
from ml_analyser.execution.workspace import IsolatedWorkspaceManager, WorkspaceHandle
from ml_analyser.persistence.sqlite import SQLiteRunStore


class BackendBenchmarkPlan(StrictModel):
    run_id: str
    project_id: str
    project_path: str
    source_fingerprint: str
    success_contract: SuccessContract
    manifest: BackendBenchmarkManifest
    hypothesis: Hypothesis
    experiment: ExperimentSpec


class BackendPrepareResult(StrictModel):
    plan: BackendBenchmarkPlan
    approval: ApprovalRecord
    inventory: RepositoryInventory
    state_graph: ProjectStateGraph
    evidence: list[EvidenceRecord]
    warnings: list[str] = Field(default_factory=list)


class BackendExecutionResult(StrictModel):
    run_id: str
    project_id: str
    final_state: RunState
    state_history: list[RunState]
    approval: ApprovalRecord
    baseline: BackendObservation
    candidate: BackendObservation
    evidence: list[EvidenceRecord]
    experiments: list[ExperimentSpec]
    decision: DecisionRecord
    disposition: Literal["retained", "discarded"]
    retained_candidate_workspace: str | None
    original_project_modified: bool = False
    applied_changes: list[str]
    warnings: list[str] = Field(default_factory=list)


class BackendBenchmarkPipeline:
    """Prepare and execute one approval-gated backend experiment."""

    def __init__(
        self,
        *,
        provider: ModelProvider,
        inspector: RepositoryInspector,
        approvals: ApprovalService,
        evaluator: DecisionEvaluator,
        workspaces: IsolatedWorkspaceManager,
        store: SQLiteRunStore,
        adapter: BackendHttpBenchmarkAdapter | None = None,
        graph_builder: InventoryStateGraphBuilder | None = None,
    ) -> None:
        self._provider = provider
        self._inspector = inspector
        self._approvals = approvals
        self._evaluator = evaluator
        self._workspaces = workspaces
        self._store = store
        self._adapter = adapter or BackendHttpBenchmarkAdapter()
        self._graph_builder = graph_builder or InventoryStateGraphBuilder()

    async def prepare(
        self,
        *,
        project_id: str,
        project_path: str,
        project_root: Path,
        success_contract: SuccessContract,
    ) -> BackendPrepareResult:
        self._validate_contract(success_contract)
        inventory = self._inspector.inspect(str(project_root))
        state_graph = self._graph_builder.build(project_id, inventory)
        source_fingerprint = self._inventory_fingerprint(project_id, inventory)
        manifest = self._adapter.load_manifest(project_root)
        run_id = str(uuid4())
        inventory_evidence = EvidenceRecord(
            id=stable_id("evidence", run_id, "inventory"),
            kind=EvidenceKind.INVENTORY,
            claim=(
                f"Observed {inventory.total_files} files and a valid backend benchmark manifest."
            ),
            source=inventory.project_root,
            content_hash=source_fingerprint,
            metadata={"adapter": self._adapter.name, "total_files": inventory.total_files},
        )
        context = AnalysisContext(
            project_id=project_id,
            success_contract=success_contract,
            inventory=inventory,
            state_graph=state_graph,
            evidence=[inventory_evidence],
        )
        hypotheses = await self._provider.propose_hypotheses(context)
        hypothesis = next(
            (item for item in hypotheses if item.kind is HypothesisKind.OPTIMIZATION),
            None,
        )
        if hypothesis is None:
            raise BackendAdapterError("provider did not produce a backend optimization hypothesis")

        experiment = ExperimentSpec(
            id=stable_id("experiment", run_id, "backend-candidate"),
            hypothesis_id=hypothesis.id,
            title="Controlled backend configuration benchmark",
            change_summary=[
                f"Set {key} to {value!r}"
                for key, value in sorted(manifest.candidate_overrides.items())
            ],
            procedure=[
                "Copy the accepted project into separate baseline and candidate workspaces.",
                "Apply only manifest-declared JSON overrides to the candidate copy.",
                "Launch each Python backend without a shell and bind it to localhost.",
                "Measure both copies with identical request counts and timeouts.",
                "Evaluate the objective, response integrity, guardrails, and budget.",
                "Retain an accepted candidate copy or discard a rejected candidate copy.",
            ],
            command=["python-isolated", manifest.entrypoint],
            measurements=sorted(
                {
                    success_contract.objective.metric,
                    *(constraint.metric for constraint in success_contract.constraints),
                }
            ),
            requires_approval=True,
            status=ExperimentStatus.AWAITING_APPROVAL,
        )
        plan = BackendBenchmarkPlan(
            run_id=run_id,
            project_id=project_id,
            project_path=project_path,
            source_fingerprint=source_fingerprint,
            success_contract=success_contract,
            manifest=manifest,
            hypothesis=hypothesis,
            experiment=experiment,
        )
        approval = self._approvals.request(
            run_id=run_id,
            experiment_id=experiment.id,
            scope=plan,
            summary=(
                "Execute the manifest-declared Python backend in two isolated local workspaces and "
                "send bounded localhost benchmark requests."
            ),
            risk_level=RiskLevel.HIGH,
        )
        self._store.append(run_id, inventory_evidence)
        return BackendPrepareResult(
            plan=plan,
            approval=approval,
            inventory=inventory,
            state_graph=state_graph,
            evidence=[inventory_evidence],
            warnings=[
                "Preparation is read-only; no project process has been started.",
                "Approval is single-use and bound to the exact returned plan fingerprint.",
                "This local isolation is not an OS-level sandbox for arbitrary untrusted code.",
            ],
        )

    def execute(
        self,
        *,
        plan: BackendBenchmarkPlan,
        approval_id: str,
        project_root: Path,
    ) -> BackendExecutionResult:
        current_inventory = self._inspector.inspect(str(project_root))
        current_fingerprint = self._inventory_fingerprint(plan.project_id, current_inventory)
        if current_fingerprint != plan.source_fingerprint:
            raise BackendAdapterError(
                "project state changed after approval preparation; prepare a new experiment"
            )
        approval = self._approvals.authorize(approval_id, plan)

        lifecycle = RunLifecycle()
        for state in (
            RunState.INGESTING,
            RunState.DIAGNOSING,
            RunState.HYPOTHESIZING,
            RunState.DESIGNING,
            RunState.SELECTING,
            RunState.AWAITING_APPROVAL,
            RunState.EXECUTING,
        ):
            lifecycle.transition(state)

        baseline_handle: WorkspaceHandle | None = None
        candidate_handle: WorkspaceHandle | None = None
        candidate_retained = False
        try:
            baseline_handle = self._workspaces.create(
                run_id=plan.run_id,
                label="baseline",
                source_root=project_root,
            )
            candidate_handle = self._workspaces.create(
                run_id=plan.run_id,
                label="candidate",
                source_root=project_root,
            )
            baseline_manifest = self._adapter.load_manifest(baseline_handle.workspace_root)
            candidate_manifest = self._adapter.load_manifest(candidate_handle.workspace_root)
            applied_changes = self._adapter.apply_candidate(
                candidate_handle.workspace_root, candidate_manifest
            )

            started = perf_counter()
            baseline = self._adapter.measure(baseline_handle.workspace_root, baseline_manifest)
            candidate = self._adapter.measure(candidate_handle.workspace_root, candidate_manifest)
            elapsed = perf_counter() - started
            lifecycle.transition(RunState.MEASURING)

            baseline_evidence = self._observation_evidence(
                run_id=plan.run_id,
                label="baseline",
                observation=baseline,
                source_fingerprint=plan.source_fingerprint,
            )
            candidate_evidence = self._observation_evidence(
                run_id=plan.run_id,
                label="candidate",
                observation=candidate,
                source_fingerprint=plan.source_fingerprint,
            )
            evidence = [baseline_evidence, candidate_evidence]
            lifecycle.transition(RunState.DECIDING)
            decision = self._evaluator.evaluate(
                experiment_id=plan.experiment.id,
                contract=plan.success_contract,
                baseline=self._measurements(
                    baseline,
                    evidence_id=baseline_evidence.id,
                    response_matches=1.0,
                ),
                candidate=self._measurements(
                    candidate,
                    evidence_id=candidate_evidence.id,
                    response_matches=float(
                        baseline.response_hash is not None
                        and baseline.response_hash == candidate.response_hash
                    ),
                ),
                usage=ResourceUsage(wall_clock_seconds=elapsed, experiments=1),
            )

            baseline_experiment = ExperimentSpec(
                id=stable_id("experiment", plan.run_id, "backend-baseline"),
                hypothesis_id=stable_id("hypothesis", plan.run_id, "backend-baseline"),
                title="Backend benchmark baseline",
                change_summary=["No project changes."],
                procedure=plan.experiment.procedure,
                command=plan.experiment.command,
                measurements=plan.experiment.measurements,
                requires_approval=False,
                status=ExperimentStatus.MEASURED,
            )
            final_status = {
                DecisionStatus.ACCEPTED: ExperimentStatus.ACCEPTED,
                DecisionStatus.REJECTED: ExperimentStatus.REJECTED,
                DecisionStatus.INCONCLUSIVE: ExperimentStatus.INCONCLUSIVE,
            }[decision.status]
            candidate_experiment = plan.experiment.model_copy(
                update={
                    "parent_experiment_id": baseline_experiment.id,
                    "status": final_status,
                }
            )
            for item in evidence:
                self._store.append(plan.run_id, item)
            self._store.add_experiment(plan.run_id, baseline_experiment)
            self._store.add_experiment(plan.run_id, candidate_experiment)

            self._workspaces.discard(baseline_handle)
            baseline_handle = None
            if decision.status is DecisionStatus.ACCEPTED:
                retained_path = self._workspaces.retain(candidate_handle)
                candidate_retained = True
                disposition: Literal["retained", "discarded"] = "retained"
            else:
                self._workspaces.discard(candidate_handle)
                candidate_handle = None
                retained_path = None
                disposition = "discarded"

            lifecycle.transition(RunState.REPORTING)
            lifecycle.transition(RunState.COMPLETED)
            return BackendExecutionResult(
                run_id=plan.run_id,
                project_id=plan.project_id,
                final_state=lifecycle.current,
                state_history=lifecycle.history,
                approval=approval,
                baseline=baseline,
                candidate=candidate,
                evidence=evidence,
                experiments=[baseline_experiment, candidate_experiment],
                decision=decision,
                disposition=disposition,
                retained_candidate_workspace=(str(retained_path) if retained_path else None),
                applied_changes=applied_changes,
                warnings=[
                    "The original project was not modified.",
                    "Accepted candidates remain isolated until a separate promotion workflow "
                    "exists.",
                    "Process isolation is local workspace isolation, not an OS-level sandbox.",
                ],
            )
        finally:
            if baseline_handle is not None and baseline_handle.workspace_root.exists():
                self._workspaces.discard(baseline_handle)
            if (
                candidate_handle is not None
                and not candidate_retained
                and candidate_handle.workspace_root.exists()
            ):
                self._workspaces.discard(candidate_handle)

    def _validate_contract(self, contract: SuccessContract) -> None:
        requested = {
            contract.objective.metric,
            *(constraint.metric for constraint in contract.constraints),
        }
        unsupported = sorted(requested - self._adapter.supported_metrics)
        if unsupported:
            raise BackendAdapterError(
                f"unsupported backend benchmark metric(s): {', '.join(unsupported)}"
            )
        if (
            "latency" in contract.objective.metric
            and contract.objective.direction is not MetricDirection.MINIMIZE
        ):
            raise BackendAdapterError("latency objectives must use 'minimize'")
        if (
            contract.objective.metric == "throughput_requests_per_second"
            and contract.objective.direction is not MetricDirection.MAXIMIZE
        ):
            raise BackendAdapterError("throughput objectives must use 'maximize'")

    @staticmethod
    def _inventory_fingerprint(project_id: str, inventory: RepositoryInventory) -> str:
        return stable_id(
            "snapshot",
            project_id,
            *(f"{item.path}:{item.sha256 or item.hash_status}" for item in inventory.files),
        )

    @staticmethod
    def _observation_evidence(
        *,
        run_id: str,
        label: str,
        observation: BackendObservation,
        source_fingerprint: str,
    ) -> EvidenceRecord:
        return EvidenceRecord(
            id=stable_id("evidence", run_id, label, "backend-observation"),
            kind=EvidenceKind.MEASUREMENT,
            claim=(
                f"{label.title()} backend: p95={observation.p95_latency_ms:.3f} ms, "
                f"mean={observation.mean_latency_ms:.3f} ms, "
                f"errors={observation.error_count}/{observation.requests}."
            ),
            source="backend_http_adapter",
            content_hash=source_fingerprint,
            metadata={
                "p95_latency_ms": observation.p95_latency_ms,
                "error_rate": observation.error_rate,
                "response_hash": observation.response_hash,
            },
        )

    @staticmethod
    def _measurements(
        observation: BackendObservation,
        *,
        evidence_id: str,
        response_matches: float,
    ) -> list[Measurement]:
        values = {
            "error_rate": observation.error_rate,
            "mean_latency_ms": observation.mean_latency_ms,
            "p50_latency_ms": observation.p50_latency_ms,
            "p95_latency_ms": observation.p95_latency_ms,
            "response_hash_matches": response_matches,
            "throughput_requests_per_second": observation.throughput_requests_per_second,
        }
        return [
            Measurement(metric=metric, value=value, evidence_ids=[evidence_id])
            for metric, value in values.items()
        ]
