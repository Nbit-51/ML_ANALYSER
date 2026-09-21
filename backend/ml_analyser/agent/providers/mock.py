"""Deterministic provider for offline development and repeatable tests."""

from ml_analyser.agent.ids import stable_id
from ml_analyser.agent.models import (
    AnalysisContext,
    FileCategory,
    Hypothesis,
    HypothesisKind,
    MetricExpectation,
)

ML_PATH_MARKERS = ("dataset", "evaluate", "inference", "model", "predict", "train")
CLASSIFICATION_METRICS = frozenset({"accuracy", "ap", "f1", "precision", "recall", "roc_auc"})


class DeterministicMockProvider:
    """Generate rule-based hypotheses without network or model calls."""

    @property
    def name(self) -> str:
        return "deterministic-local"

    async def propose_hypotheses(self, context: AnalysisContext) -> list[Hypothesis]:
        if not context.evidence:
            raise ValueError("analysis context must contain observed evidence")

        evidence_id = context.evidence[0].id
        objective = context.success_contract.objective
        hypotheses = [
            Hypothesis(
                id=stable_id("hypothesis", context.project_id, "baseline", objective.metric),
                kind=HypothesisKind.BASELINE,
                statement=(
                    f"The current project can produce a reproducible baseline for "
                    f"'{objective.metric}'."
                ),
                rationale=(
                    "No candidate change can be evaluated safely until a compatible baseline "
                    "measurement is captured from the accepted project state."
                ),
                proposed_intervention=(
                    "Run the domain adapter's baseline measurement without modifying project code."
                ),
                expected_outcome=MetricExpectation(
                    metric=objective.metric,
                    direction=objective.direction,
                    minimum_delta=0.0,
                ),
                rejection_criteria=(
                    f"Reject the baseline procedure if it cannot produce a valid "
                    f"'{objective.metric}' measurement with provenance."
                ),
                evidence_ids=[evidence_id],
                priority=100,
            )
        ]

        paths = [file.path.casefold() for file in context.inventory.files]
        has_ml_signal = any(marker in path for path in paths for marker in ML_PATH_MARKERS) or any(
            file.category in {FileCategory.MODEL_ARTIFACT, FileCategory.NOTEBOOK}
            for file in context.inventory.files
        )

        if has_ml_signal and objective.metric.casefold() in CLASSIFICATION_METRICS:
            hypotheses.append(
                Hypothesis(
                    id=stable_id("hypothesis", context.project_id, "threshold", objective.metric),
                    kind=HypothesisKind.DIAGNOSTIC,
                    statement=(
                        f"The observed '{objective.metric}' may be limited by decision-threshold "
                        "calibration rather than model weights."
                    ),
                    rationale=(
                        "A threshold sweep is a cheap, information-rich diagnostic when a "
                        "classification project exposes scores or probabilities."
                    ),
                    proposed_intervention=(
                        "If the ML adapter confirms compatible classifier outputs, evaluate a "
                        "threshold sweep on the existing validation predictions without retraining."
                    ),
                    expected_outcome=MetricExpectation(
                        metric=objective.metric,
                        direction=objective.direction,
                        minimum_delta=objective.minimum_improvement,
                    ),
                    rejection_criteria=(
                        "Reject if no valid threshold satisfies the objective and every configured "
                        "guardrail on the same validation split."
                    ),
                    evidence_ids=[evidence_id],
                    priority=80,
                )
            )

        has_backend_manifest = any(path.endswith("backend_benchmark.json") for path in paths)
        if has_backend_manifest:
            hypotheses.append(
                Hypothesis(
                    id=stable_id(
                        "hypothesis", context.project_id, "backend-benchmark", objective.metric
                    ),
                    kind=HypothesisKind.OPTIMIZATION,
                    statement=(
                        f"The manifest-declared backend configuration change may improve "
                        f"'{objective.metric}' without violating response-integrity guardrails."
                    ),
                    rationale=(
                        "A controlled baseline/candidate benchmark can verify the measurable "
                        "effect before any accepted project state is changed."
                    ),
                    proposed_intervention=(
                        "Apply only the manifest-declared configuration overrides in an isolated "
                        "candidate workspace and benchmark both copies with the same localhost "
                        "request procedure."
                    ),
                    expected_outcome=MetricExpectation(
                        metric=objective.metric,
                        direction=objective.direction,
                        minimum_delta=objective.minimum_improvement,
                    ),
                    rejection_criteria=(
                        "Reject if the objective fails, any guardrail fails, the response changes, "
                        "or the observed resource usage exceeds budget."
                    ),
                    evidence_ids=[evidence_id],
                    priority=90,
                )
            )

        return hypotheses
