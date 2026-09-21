"""Approval workflow with tamper-proof, single-use authorization."""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel

from ml_analyser.agent.ids import model_fingerprint
from ml_analyser.agent.models import (
    ApprovalRecord,
    ApprovalStatus,
    RiskLevel,
)
from ml_analyser.agent.ports import ApprovalStore


class ApprovalService:
    """Create, decide, and consume persisted execution approvals."""

    def __init__(self, store: ApprovalStore) -> None:
        self._store = store

    def request(
        self,
        *,
        run_id: str,
        experiment_id: str,
        scope: BaseModel,
        summary: str,
        risk_level: RiskLevel,
    ) -> ApprovalRecord:
        approval = ApprovalRecord(
            id=str(uuid4()),
            run_id=run_id,
            experiment_id=experiment_id,
            scope_fingerprint=model_fingerprint(scope),
            summary=summary,
            risk_level=risk_level,
        )
        self._store.create_approval(approval)
        return approval

    def decide(
        self,
        approval_id: str,
        *,
        approved: bool,
        reason: str | None = None,
    ) -> ApprovalRecord:
        return self._store.decide_approval(
            approval_id,
            status=ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED,
            reason=reason,
        )

    def authorize(self, approval_id: str, scope: BaseModel) -> ApprovalRecord:
        """Verify that the unchanged approved scope is authorized exactly once."""
        return self._store.consume_approval(approval_id, model_fingerprint(scope))
