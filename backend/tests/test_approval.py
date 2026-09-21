"""Tests for persisted, fingerprint-bound, single-use approvals."""

from pathlib import Path

import pytest

from ml_analyser.agent.approval import ApprovalService
from ml_analyser.agent.models import (
    ApprovalStatus,
    MetricDirection,
    Objective,
    RiskLevel,
    SuccessContract,
)
from ml_analyser.persistence.sqlite import (
    InvalidApprovalTransitionError,
    SQLiteRunStore,
)


def _scope(metric: str = "p95_latency_ms") -> SuccessContract:
    return SuccessContract(objective=Objective(metric=metric, direction=MetricDirection.MINIMIZE))


def test_approved_scope_can_be_consumed_exactly_once(tmp_path: Path) -> None:
    service = ApprovalService(SQLiteRunStore(tmp_path / "approvals.db"))
    approval = service.request(
        run_id="run-1",
        experiment_id="experiment-1",
        scope=_scope(),
        summary="Run benchmark.",
        risk_level=RiskLevel.HIGH,
    )

    assert approval.status is ApprovalStatus.PENDING
    decided = service.decide(approval.id, approved=True, reason="Reviewed")
    consumed = service.authorize(approval.id, _scope())

    assert decided.status is ApprovalStatus.APPROVED
    assert consumed.status is ApprovalStatus.CONSUMED
    with pytest.raises(InvalidApprovalTransitionError, match="consumed"):
        service.authorize(approval.id, _scope())


def test_tampered_scope_cannot_use_existing_approval(tmp_path: Path) -> None:
    service = ApprovalService(SQLiteRunStore(tmp_path / "approvals.db"))
    approval = service.request(
        run_id="run-1",
        experiment_id="experiment-1",
        scope=_scope(),
        summary="Run benchmark.",
        risk_level=RiskLevel.HIGH,
    )
    service.decide(approval.id, approved=True)

    with pytest.raises(InvalidApprovalTransitionError, match="fingerprint"):
        service.authorize(approval.id, _scope("mean_latency_ms"))


def test_rejected_scope_cannot_be_authorized(tmp_path: Path) -> None:
    service = ApprovalService(SQLiteRunStore(tmp_path / "approvals.db"))
    approval = service.request(
        run_id="run-1",
        experiment_id="experiment-1",
        scope=_scope(),
        summary="Run benchmark.",
        risk_level=RiskLevel.HIGH,
    )
    service.decide(approval.id, approved=False, reason="Too risky")

    with pytest.raises(InvalidApprovalTransitionError, match="rejected"):
        service.authorize(approval.id, _scope())
