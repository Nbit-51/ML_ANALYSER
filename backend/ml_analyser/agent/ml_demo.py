"""End-to-end hidden threshold-failure demonstration service."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from uuid import uuid4

from pydantic import Field

from ml_analyser.adapters.ml_threshold import (
    AdapterValidationError,
    ClassificationThresholdAdapter,
    ThresholdObservation,
)
from ml_analyser.agent.evaluator import DecisionEvaluator
from ml_analyser.agent.ids import stable_id
from ml_analyser.agent.models import (
    AnalysisContext,
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
    RunState,
    StrictModel,
    SuccessContract,
)
from ml_analyser.agent.ports import ModelProvider, RepositoryInspector
from ml_analyser.agent.state import RunLifecycle
from ml_analyser.agent.state_graph import InventoryStateGraphBuilder
from ml_analyser.persistence.sqlite import SQLiteRunStore


class ThresholdDemoResult(StrictModel):
    run_id: str
    project_id: str
    provider: str
    final_state: RunState
    state_history: list[RunState]
    inventory: RepositoryInventory
    state_graph: ProjectStateGraph
    hypothesis: Hypothesis
    baseline: ThresholdObservation
    candidate: ThresholdObservation
    evidence: list[EvidenceRecord]
    experiments: list[ExperimentSpec]
    decision: DecisionRecord
    recommendation: str
    persisted: bool
    warnings: list[str] = Field(default_factory=list)


class ThresholdDemoService:
    """Run a bounded, data-only threshold experiment and persist its provenance."""

    def __init__(
        self,
        *,
        provider: ModelProvider,
        inspector: RepositoryInspector,
        evaluator: DecisionEvaluator,
        store: SQLiteRunStore | None = None,
        adapter: ClassificationThresholdAdapter | None = None,
        graph_builder: InventoryStateGraphBuilder | None = None,
    ) -> None:
        self._provider = provider
        self._inspector = inspector
        self._evaluator = evaluator
        self._store = store
        self._adapter = adapter or ClassificationThresholdAdapter()
        self._graph_builder = graph_builder or InventoryStateGraphBuilder()

    async def run(
        self,
        *,
        project_id: str,
        project_root: Path,
        success_contract: SuccessContract,
    ) -> ThresholdDemoResult:
        if success_contract.objective.direction is not MetricDirection.MAXIMIZE:
            raise AdapterValidationError("threshold demo objectives must use 'maximize'")
        requested_metrics = {
            success_contract.objective.metric,
            *(constraint.metric for constraint in success_contract.constraints),
        }
        unsupported = sorted(requested_metrics - self._adapter.supported_metrics)
        if unsupported:
            raise AdapterValidationError(
                f"unsupported threshold-demo metric(s): {', '.join(unsupported)}"
            )

        run_id = str(uuid4())
        lifecycle = RunLifecycle()
        lifecycle.transition(RunState.INGESTING)
        inventory = self._inspector.inspect(str(project_root))
        state_graph = self._graph_builder.build(project_id, inventory)
        manifest, rows = self._adapter.load(project_root)
        predictions_hash = self._adapter.predictions_hash(project_root, manifest)

        inventory_evidence = EvidenceRecord(
            id=stable_id("evidence", run_id, "inventory"),
            kind=EvidenceKind.INVENTORY,
            claim=f"Observed {inventory.total_files} project files and validated {len(rows)} rows.",
            source=inventory.project_root,
            content_hash=predictions_hash,
            metadata={"rows": len(rows), "adapter": self._adapter.name},
        )
        lifecycle.transition(RunState.DIAGNOSING)
        context = AnalysisContext(
            project_id=project_id,
            success_contract=success_contract,
            inventory=inventory,
            state_graph=state_graph,
            evidence=[inventory_evidence],
        )

        lifecycle.transition(RunState.HYPOTHESIZING)
        hypotheses = await self._provider.propose_hypotheses(context)
        hypothesis = next(
            (item for item in hypotheses if item.kind is HypothesisKind.DIAGNOSTIC),
            None,
        )
        if hypothesis is None:
            raise AdapterValidationError(
                "provider did not produce a compatible threshold-calibration hypothesis"
            )

        lifecycle.transition(RunState.DESIGNING)
        baseline_experiment = ExperimentSpec(
            id=stable_id("experiment", run_id, "baseline"),
            hypothesis_id=stable_id("hypothesis", run_id, "baseline"),
            title="Measure configured classification threshold",
            change_summary=["No project change; observe the configured baseline threshold."],
            procedure=["Measure saved validation predictions at the configured threshold."],
            measurements=sorted(requested_metrics),
            requires_approval=False,
            status=ExperimentStatus.MEASURED,
        )
        candidate_experiment = ExperimentSpec(
            id=stable_id("experiment", run_id, "threshold-sweep"),
            hypothesis_id=hypothesis.id,
            title="Controlled decision-threshold sweep",
            parent_experiment_id=baseline_experiment.id,
            change_summary=["Evaluate thresholds without retraining or modifying model weights."],
            procedure=[
                "Enumerate score-derived threshold candidates.",
                "Measure each candidate on the same saved validation predictions.",
                "Select by objective, then evaluate all configured guardrails and budget limits.",
            ],
            measurements=sorted(requested_metrics),
            requires_approval=True,
            status=ExperimentStatus.APPROVED,
        )

        lifecycle.transition(RunState.SELECTING)
        lifecycle.transition(RunState.AWAITING_APPROVAL)
        lifecycle.transition(RunState.EXECUTING)
        started_at = perf_counter()
        baseline = self._adapter.measure(rows, manifest.baseline_threshold)
        candidate = self._adapter.find_best_threshold(
            rows,
            objective_metric=success_contract.objective.metric,
        )
        elapsed = perf_counter() - started_at

        lifecycle.transition(RunState.MEASURING)
        baseline_evidence = self._measurement_evidence(
            run_id=run_id,
            label="baseline",
            observation=baseline,
            source=manifest.predictions_file,
            content_hash=predictions_hash,
        )
        candidate_evidence = self._measurement_evidence(
            run_id=run_id,
            label="candidate",
            observation=candidate,
            source=manifest.predictions_file,
            content_hash=predictions_hash,
        )
        evidence = [inventory_evidence, baseline_evidence, candidate_evidence]

        baseline_measurements = self._measurements(baseline, baseline_evidence.id)
        candidate_measurements = self._measurements(candidate, candidate_evidence.id)
        lifecycle.transition(RunState.DECIDING)
        decision = self._evaluator.evaluate(
            experiment_id=candidate_experiment.id,
            contract=success_contract,
            baseline=baseline_measurements,
            candidate=candidate_measurements,
            usage=ResourceUsage(wall_clock_seconds=elapsed, experiments=1),
        )
        final_experiment_status = {
            DecisionStatus.ACCEPTED: ExperimentStatus.ACCEPTED,
            DecisionStatus.REJECTED: ExperimentStatus.REJECTED,
            DecisionStatus.INCONCLUSIVE: ExperimentStatus.INCONCLUSIVE,
        }[decision.status]
        candidate_experiment = candidate_experiment.model_copy(
            update={"status": final_experiment_status}
        )

        persisted = False
        if self._store is not None:
            for item in evidence:
                self._store.append(run_id, item)
            self._store.add_experiment(run_id, baseline_experiment)
            self._store.add_experiment(run_id, candidate_experiment)
            persisted = True

        lifecycle.transition(RunState.REPORTING)
        lifecycle.transition(RunState.COMPLETED)
        recommendation = self._recommendation(decision, baseline, candidate)
        return ThresholdDemoResult(
            run_id=run_id,
            project_id=project_id,
            provider=self._provider.name,
            final_state=lifecycle.current,
            state_history=lifecycle.history,
            inventory=inventory,
            state_graph=state_graph,
            hypothesis=hypothesis,
            baseline=baseline,
            candidate=candidate,
            evidence=evidence,
            experiments=[baseline_experiment, candidate_experiment],
            decision=decision,
            recommendation=recommendation,
            persisted=persisted,
            warnings=[
                "This adapter measures saved validation predictions; it does not retrain a model.",
                "The accepted project files were not modified by this experiment.",
            ],
        )

    @staticmethod
    def _measurement_evidence(
        *,
        run_id: str,
        label: str,
        observation: ThresholdObservation,
        source: str,
        content_hash: str,
    ) -> EvidenceRecord:
        metrics = ", ".join(
            f"{name}={value:.6f}" for name, value in sorted(observation.metrics.items())
        )
        return EvidenceRecord(
            id=stable_id("evidence", run_id, label, str(observation.threshold)),
            kind=EvidenceKind.MEASUREMENT,
            claim=f"{label.title()} threshold={observation.threshold:.6f}: {metrics}.",
            source=source,
            content_hash=content_hash,
            metadata={"threshold": observation.threshold, "rows": observation.sample_count},
        )

    @staticmethod
    def _measurements(observation: ThresholdObservation, evidence_id: str) -> list[Measurement]:
        return [
            Measurement(metric=metric, value=value, evidence_ids=[evidence_id])
            for metric, value in observation.metrics.items()
        ]

    @staticmethod
    def _recommendation(
        decision: DecisionRecord,
        baseline: ThresholdObservation,
        candidate: ThresholdObservation,
    ) -> str:
        if decision.status is DecisionStatus.ACCEPTED:
            return (
                f"Accept threshold {candidate.threshold:.6f} instead of "
                f"{baseline.threshold:.6f}; the objective and all guardrails passed."
            )
        if decision.status is DecisionStatus.REJECTED:
            return (
                f"Keep threshold {baseline.threshold:.6f}; the candidate failed at least one "
                "objective, guardrail, or budget check."
            )
        return (
            f"Keep threshold {baseline.threshold:.6f}; evidence was insufficient for a safe change."
        )
