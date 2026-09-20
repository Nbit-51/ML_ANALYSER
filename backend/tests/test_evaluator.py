"""Tests for deterministic objective, guardrail, and budget decisions."""

import pytest

from ml_analyser.agent.evaluator import DecisionEvaluator
from ml_analyser.agent.models import (
    ComputeBudget,
    ConstraintOperator,
    DecisionStatus,
    Measurement,
    MetricConstraint,
    MetricDirection,
    Objective,
    ResourceUsage,
    SuccessContract,
)


def _contract() -> SuccessContract:
    return SuccessContract(
        objective=Objective(
            metric="f1",
            direction=MetricDirection.MAXIMIZE,
            target=0.75,
            minimum_improvement=0.01,
        ),
        constraints=[
            MetricConstraint(
                metric="latency_ms",
                operator=ConstraintOperator.LT,
                threshold=100,
            )
        ],
        budget=ComputeBudget(max_cost_usd=1.0, max_experiments=2),
    )


def _measurement(metric: str, value: float, evidence_id: str) -> Measurement:
    return Measurement(metric=metric, value=value, evidence_ids=[evidence_id])


def test_accepts_only_when_objective_guardrails_and_budget_pass() -> None:
    decision = DecisionEvaluator().evaluate(
        experiment_id="experiment-1",
        contract=_contract(),
        baseline=[_measurement("f1", 0.72, "baseline-f1")],
        candidate=[
            _measurement("f1", 0.76, "candidate-f1"),
            _measurement("latency_ms", 95, "candidate-latency"),
        ],
        usage=ResourceUsage(cost_usd=0.25),
    )

    assert decision.status is DecisionStatus.ACCEPTED
    assert decision.objective is not None
    assert decision.objective.improvement == pytest.approx(0.04)
    assert decision.constraints[0].passed
    assert decision.budget.passed


def test_rejects_improvement_that_breaks_a_guardrail() -> None:
    decision = DecisionEvaluator().evaluate(
        experiment_id="experiment-2",
        contract=_contract(),
        baseline=[_measurement("f1", 0.72, "baseline-f1")],
        candidate=[
            _measurement("f1", 0.80, "candidate-f1"),
            _measurement("latency_ms", 125, "candidate-latency"),
        ],
        usage=ResourceUsage(cost_usd=0.25),
    )

    assert decision.status is DecisionStatus.REJECTED
    assert decision.objective is not None and decision.objective.passed
    assert not decision.constraints[0].passed
    assert decision.reason == "Rejected because the guardrail check failed."


def test_marks_missing_measurement_inconclusive_instead_of_successful() -> None:
    decision = DecisionEvaluator().evaluate(
        experiment_id="experiment-3",
        contract=_contract(),
        baseline=[_measurement("f1", 0.72, "baseline-f1")],
        candidate=[_measurement("f1", 0.80, "candidate-f1")],
        usage=ResourceUsage(),
    )

    assert decision.status is DecisionStatus.INCONCLUSIVE
    assert "latency_ms" in decision.reason


def test_rejects_candidate_that_exceeds_budget() -> None:
    decision = DecisionEvaluator().evaluate(
        experiment_id="experiment-4",
        contract=_contract(),
        baseline=[_measurement("f1", 0.72, "baseline-f1")],
        candidate=[
            _measurement("f1", 0.80, "candidate-f1"),
            _measurement("latency_ms", 90, "candidate-latency"),
        ],
        usage=ResourceUsage(cost_usd=1.50),
    )

    assert decision.status is DecisionStatus.REJECTED
    assert decision.budget.violations == ["cost_usd: used 1.5, limit 1.0"]
