"""Approval-gated, measured ML training experiment."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from ml_analyser.adapters.ml_training import (
    MlTrainingAdapter,
    MlTrainingError,
    MlTrainingManifest,
    MlTrainingObservation,
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


class MlTrainingPlan(StrictModel):
    run_id: str
    project_id: str
    project_path: str
    source_fingerprint: str
    success_contract: SuccessContract
    manifest: MlTrainingManifest
    hypothesis: Hypothesis
    experiment: ExperimentSpec


class MlTrainingPrepareResult(StrictModel):
    plan: MlTrainingPlan
    approval: ApprovalRecord
    inventory: RepositoryInventory
    state_graph: ProjectStateGraph
    evidence: list[EvidenceRecord]


class MlTrainingResult(StrictModel):
    run_id: str
    project_id: str
    final_state: RunState
    state_history: list[RunState]
    approval: ApprovalRecord
    baseline: MlTrainingObservation
    candidate: MlTrainingObservation
    evidence: list[EvidenceRecord]
    experiments: list[ExperimentSpec]
    decision: DecisionRecord
    disposition: str
    retained_candidate_workspace: str | None
    applied_changes: list[str]
    original_project_modified: bool = False


class MlTrainingPipeline:
    """Build a falsifiable plan, then execute its exact approved scope."""

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
        self._provider = provider
        self._inspector = inspector
        self._approvals = approvals
        self._evaluator = evaluator
        self._workspaces = workspaces
        self._store = store
        self._adapter = MlTrainingAdapter()

    async def prepare(
        self,
        *,
        project_id: str,
        project_path: str,
        project_root: Path,
        success_contract: SuccessContract,
    ) -> MlTrainingPrepareResult:
        inventory = self._inspector.inspect(str(project_root))
        graph = InventoryStateGraphBuilder().build(project_id, inventory)
        fingerprint = self._fingerprint(project_id, inventory)
        manifest = self._adapter.load_manifest(project_root)
        self._validate_contract(success_contract, manifest)
        run_id = str(uuid4())
        evidence = EvidenceRecord(
            id=stable_id("evidence", run_id, "ml-inventory"),
            kind=EvidenceKind.INVENTORY,
            claim=f"Observed {inventory.total_files} files and a declared ML training experiment.",
            source=inventory.project_root,
            content_hash=fingerprint,
            metadata={
                "adapter": self._adapter.name,
                "total_files": inventory.total_files,
                "entrypoint": manifest.entrypoint,
                "config_file": manifest.config_file,
                "candidate_overrides": json.dumps(manifest.candidate_overrides, sort_keys=True),
                "metrics_file": manifest.metrics_file,
            },
        )
        context = AnalysisContext(
            project_id=project_id,
            success_contract=success_contract,
            inventory=inventory,
            state_graph=graph,
            evidence=[evidence],
        )
        hypotheses = await self._provider.propose_hypotheses(context)
        hypothesis = next(
            (
                item
                for item in hypotheses
                if item.kind is HypothesisKind.OPTIMIZATION
                and item.expected_outcome.metric == success_contract.objective.metric
            ),
            None,
        )
        if hypothesis is None:
            raise MlTrainingError("provider did not produce a compatible ML hypothesis")
        experiment = ExperimentSpec(
            id=stable_id("experiment", run_id, "ml-candidate"),
            hypothesis_id=hypothesis.id,
            title="Controlled ML training configuration experiment",
            change_summary=[
                f"Set {key} to {value!r}"
                for key, value in sorted(manifest.candidate_overrides.items())
            ],
            procedure=[
                "Copy the repository into separate baseline and candidate workspaces.",
                "Apply the declared JSON configuration changes only in the candidate copy.",
                "Run the declared Python training script once in each copy.",
                "Compare validation metrics against the objective, guardrails, and budget.",
                "Retain an accepted candidate copy or discard a rejected copy.",
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
        plan = MlTrainingPlan(
            run_id=run_id,
            project_id=project_id,
            project_path=project_path,
            source_fingerprint=fingerprint,
            success_contract=success_contract,
            manifest=manifest,
            hypothesis=hypothesis,
            experiment=experiment,
        )
        approval = self._approvals.request(
            run_id=run_id,
            experiment_id=experiment.id,
            scope=plan,
            summary="Run the manifest-declared training script in two isolated local copies.",
            risk_level=RiskLevel.HIGH,
        )
        self._store.append(run_id, evidence)
        return MlTrainingPrepareResult(
            plan=plan,
            approval=approval,
            inventory=inventory,
            state_graph=graph,
            evidence=[evidence],
        )

    def execute(
        self,
        *,
        plan: MlTrainingPlan,
        approval_id: str,
        project_root: Path,
        on_state: Callable[[RunState], None] | None = None,
    ) -> MlTrainingResult:
        inventory = self._inspector.inspect(str(project_root))
        if self._fingerprint(plan.project_id, inventory) != plan.source_fingerprint:
            raise MlTrainingError("project changed after preparation; prepare a new experiment")
        approval = self._approvals.authorize(approval_id, plan)
        lifecycle = RunLifecycle(on_transition=on_state)
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
        retained = False
        try:
            baseline_handle = self._workspaces.create(
                run_id=plan.run_id, label="baseline", source_root=project_root
            )
            candidate_handle = self._workspaces.create(
                run_id=plan.run_id, label="candidate", source_root=project_root
            )
            baseline_manifest = self._adapter.load_manifest(baseline_handle.workspace_root)
            candidate_manifest = self._adapter.load_manifest(candidate_handle.workspace_root)
            changes = self._adapter.apply_candidate(
                candidate_handle.workspace_root, candidate_manifest
            )
            started = perf_counter()
            baseline = self._adapter.measure(baseline_handle.workspace_root, baseline_manifest)
            candidate = self._adapter.measure(candidate_handle.workspace_root, candidate_manifest)
            elapsed = perf_counter() - started
            lifecycle.transition(RunState.MEASURING)
            baseline_evidence = self._evidence(plan, "baseline", baseline)
            candidate_evidence = self._evidence(plan, "candidate", candidate)
            lifecycle.transition(RunState.DECIDING)
            decision = self._evaluator.evaluate(
                experiment_id=plan.experiment.id,
                contract=plan.success_contract,
                baseline=self._measurements(baseline, baseline_evidence.id),
                candidate=self._measurements(candidate, candidate_evidence.id),
                usage=ResourceUsage(wall_clock_seconds=elapsed, experiments=1),
            )
            baseline_experiment = ExperimentSpec(
                id=stable_id("experiment", plan.run_id, "ml-baseline"),
                hypothesis_id=stable_id("hypothesis", plan.run_id, "ml-baseline"),
                title="ML training baseline",
                change_summary=["No project change."],
                procedure=plan.experiment.procedure,
                command=plan.experiment.command,
                measurements=plan.experiment.measurements,
                requires_approval=False,
                status=ExperimentStatus.MEASURED,
            )
            statuses = {
                DecisionStatus.ACCEPTED: ExperimentStatus.ACCEPTED,
                DecisionStatus.REJECTED: ExperimentStatus.REJECTED,
                DecisionStatus.INCONCLUSIVE: ExperimentStatus.INCONCLUSIVE,
            }
            candidate_experiment = plan.experiment.model_copy(
                update={
                    "parent_experiment_id": baseline_experiment.id,
                    "status": statuses[decision.status],
                }
            )
            for item in (baseline_evidence, candidate_evidence):
                self._store.append(plan.run_id, item)
            self._store.add_experiment(plan.run_id, baseline_experiment)
            self._store.add_experiment(plan.run_id, candidate_experiment)
            self._workspaces.discard(baseline_handle)
            baseline_handle = None
            if decision.status is DecisionStatus.ACCEPTED:
                retained_path = self._workspaces.retain(candidate_handle)
                retained = True
                disposition = "retained"
            else:
                self._workspaces.discard(candidate_handle)
                candidate_handle = None
                retained_path = None
                disposition = "discarded"
            lifecycle.transition(RunState.REPORTING)
            lifecycle.transition(RunState.COMPLETED)
            return MlTrainingResult(
                run_id=plan.run_id,
                project_id=plan.project_id,
                final_state=lifecycle.current,
                state_history=lifecycle.history,
                approval=approval,
                baseline=baseline,
                candidate=candidate,
                evidence=[baseline_evidence, candidate_evidence],
                experiments=[baseline_experiment, candidate_experiment],
                decision=decision,
                disposition=disposition,
                retained_candidate_workspace=str(retained_path) if retained_path else None,
                applied_changes=changes,
            )
        finally:
            if baseline_handle is not None and baseline_handle.workspace_root.exists():
                self._workspaces.discard(baseline_handle)
            if (
                candidate_handle is not None
                and not retained
                and candidate_handle.workspace_root.exists()
            ):
                self._workspaces.discard(candidate_handle)

    def _validate_contract(self, contract: SuccessContract, manifest: MlTrainingManifest) -> None:
        requested = {
            contract.objective.metric,
            *(constraint.metric for constraint in contract.constraints),
        }
        if not requested.issubset({m.name for m in manifest.metric_definitions}):
            raise MlTrainingError("ML training contract contains unsupported metrics")

    @staticmethod
    def _fingerprint(project_id: str, inventory: RepositoryInventory) -> str:
        return stable_id(
            "snapshot",
            project_id,
            *(f"{item.path}:{item.sha256 or item.hash_status}" for item in inventory.files),
        )

    @staticmethod
    def _evidence(
        plan: MlTrainingPlan, label: str, observation: MlTrainingObservation
    ) -> EvidenceRecord:
        return EvidenceRecord(
            id=stable_id("evidence", plan.run_id, "ml", label),
            kind=EvidenceKind.MEASUREMENT,
            claim=(
                f"{label.title()} validation: "
                + ", ".join(
                    f"{key}={value:.4f}" for key, value in sorted(observation.metrics.items())
                )
            ),
            source="ml_training_adapter",
            content_hash=plan.source_fingerprint,
            metadata={
                "sample_count": observation.sample_count,
                "duration_seconds": observation.duration_seconds,
            },
        )

    @staticmethod
    def _measurements(observation: MlTrainingObservation, evidence_id: str) -> list[Measurement]:
        return [
            Measurement(metric=key, value=value, evidence_ids=[evidence_id])
            for key, value in observation.metrics.items()
        ]
