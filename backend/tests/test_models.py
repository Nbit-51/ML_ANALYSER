"""Validation tests for core optimization-domain models."""

import pytest
from pydantic import ValidationError

from ml_analyser.agent.models import (
    ConstraintOperator,
    MetricConstraint,
    MetricDirection,
    Objective,
    SuccessContract,
)


def test_success_contract_rejects_duplicate_constraint_metrics() -> None:
    with pytest.raises(ValidationError, match="constraint metrics must be unique"):
        SuccessContract(
            objective=Objective(metric="f1", direction=MetricDirection.MAXIMIZE),
            constraints=[
                MetricConstraint(
                    metric="latency",
                    operator=ConstraintOperator.LT,
                    threshold=100,
                ),
                MetricConstraint(
                    metric="LATENCY",
                    operator=ConstraintOperator.LTE,
                    threshold=120,
                ),
            ],
        )


def test_domain_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        Objective.model_validate(
            {
                "metric": "f1",
                "direction": "maximize",
                "unsupported": True,
            }
        )
