"""Public judge experience with bounded configuration choices and explicit approval."""

from __future__ import annotations

import json
import secrets
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field

from ml_analyser.agent.approval import ApprovalService
from ml_analyser.agent.models import EvidenceKind, EvidenceRecord, RiskLevel, StrictModel
from ml_analyser.core.config import get_settings
from ml_analyser.lab.engine import (
    MAX_ATTEMPTS,
    PROTOCOL,
    Attempt,
    LabPlan,
    LabReasoner,
    Proposal,
    digest,
    measure,
    source_text,
)
from ml_analyser.lab.store import LabStore
from ml_analyser.persistence.sqlite import SQLiteRunStore

router = APIRouter(prefix="/lab", tags=["counterexample lab"])


class PrepareLab(StrictModel):
    mode: Literal["offline", "live"] = "offline"


class ExecuteLab(StrictModel):
    plan: LabPlan
    approval_id: str = Field(min_length=1, max_length=100)
    approved: Literal[True]


def stores() -> tuple[LabStore, SQLiteRunStore]:
    path = get_settings().state_database
    return LabStore(path.with_name("lab-quotas.db")), SQLiteRunStore(
        path.with_name("lab-evidence.db")
    )


def owner(request: Request) -> str:
    token = request.cookies.get("ml_lab", "")
    if len(token) < 32 or len(token) > 100:
        raise ValueError("Prepare this campaign in the same browser before approving it.")
    return digest(token)


@router.get("/status")
def status() -> dict[str, str | bool | int]:
    settings = get_settings()
    return {
        "live_available": bool(
            settings.model_provider == "nebius"
            and settings.nebius_api_key
            and settings.nebius_api_key.get_secret_value()
            and settings.nebius_model
            and settings.lab_daily_limit
        ),
        "model": settings.nebius_model or "not configured",
        "live_daily_limit": settings.lab_daily_limit,
        "protocol": PROTOCOL,
    }


@router.post("/prepare", status_code=201)
async def prepare(request: Request, response: Response, body: PrepareLab) -> dict[str, object]:
    settings = get_settings()
    if body.mode == "live" and not status()["live_available"]:
        raise HTTPException(
            503,
            "Live Nebius inference is not configured or is disabled. "
            "Offline measurements remain available.",
        )
    token = request.cookies.get("ml_lab", "")
    if not 32 <= len(token) <= 100:
        token = secrets.token_urlsafe(32)
    response.set_cookie(
        "ml_lab",
        token,
        httponly=True,
        secure=settings.app_url.startswith("https://"),
        samesite="strict",
        max_age=3600,
    )
    run_id, seed = str(uuid4()), secrets.token_hex(24)
    storage, evidence = stores()
    try:
        storage.reserve(
            run_id,
            digest(token),
            live=body.mode == "live",
            limit=settings.lab_daily_limit,
            cooldown=settings.lab_cooldown_seconds,
        )
    except ValueError as error:
        raise HTTPException(
            429, str(error), headers={"Retry-After": str(max(1, settings.lab_cooldown_seconds))}
        ) from error
    reasoner = LabReasoner(
        settings.model_copy(update={"model_provider": "nebius" if body.mode == "live" else "mock"})
    )
    try:
        proposal = await reasoner.propose([])
    except ValueError as error:
        raise HTTPException(502, str(error)) from error
    plan = LabPlan(
        run_id=run_id,
        provider=reasoner.name,
        source_sha256=digest(source_text()),
        challenge_commitment=digest(seed),
        first_proposal=proposal,
    )
    approval = ApprovalService(evidence).request(
        run_id=run_id,
        experiment_id=run_id,
        scope=plan,
        summary=(
            "Run the fixed pricing benchmark. Up to three cache-field proposals and three paired "
            "measurement rounds per proposal. No visitor code, installs, or shell commands."
        ),
        risk_level=RiskLevel.LOW,
    )
    storage.save_plan(
        run_id,
        {
            "plan": plan.model_dump(mode="json"),
            "approval_id": approval.id,
            "seed": seed,
            "mode": body.mode,
            "model_calls": reasoner.calls,
            "model_tokens": reasoner.tokens,
        },
    )
    evidence.append(
        run_id,
        EvidenceRecord(
            id=f"{run_id}:plan",
            kind=EvidenceKind.CONFIGURATION,
            claim="Challenge seed committed before approval; no benchmark executed.",
            source=PROTOCOL,
            content_hash=plan.challenge_commitment,
            metadata={"plan_json": plan.model_dump_json()},
        ),
    )
    return {"plan": plan, "approval": approval, "source": source_text()}


@router.post("/execute")
async def execute(request: Request, body: ExecuteLab) -> dict[str, object]:
    storage, evidence = stores()
    try:
        saved = storage.load(body.plan.run_id, owner(request))
        if (
            saved["plan"] != body.plan.model_dump(mode="json")
            or saved["approval_id"] != body.approval_id
        ):
            raise ValueError("Plan differs from the server-held approved scope.")
        if digest(source_text()) != body.plan.source_sha256:
            raise ValueError("Benchmark source changed. Prepare a new campaign.")
        # Conditional approval transitions make execution single-use under concurrent requests.
        approvals = ApprovalService(evidence)
        approvals.decide(body.approval_id, approved=True)
        approvals.authorize(body.approval_id, body.plan)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    settings = get_settings().model_copy(
        update={"model_provider": "nebius" if saved["mode"] == "live" else "mock"}
    )
    reasoner = LabReasoner(settings)
    if reasoner.name != body.plan.provider:
        raise HTTPException(409, "The configured provider changed. Prepare again.")
    attempts: list[Attempt] = []
    proposal = body.plan.first_proposal
    stop_reason = "Approved attempt budget reached. No accepted candidate."
    for number in range(1, MAX_ATTEMPTS + 1):
        attempt = measure(proposal, saved["seed"], number)
        attempts.append(attempt)
        evidence.append(
            body.plan.run_id,
            EvidenceRecord(
                id=f"{body.plan.run_id}:attempt:{number}",
                kind=EvidenceKind.MEASUREMENT,
                claim=f"Measured cache candidate: {attempt.decision.status.value}.",
                source=PROTOCOL,
                content_hash=digest(attempt.model_dump(mode="json")),
                metadata={"attempt_json": attempt.model_dump_json()},
            ),
        )
        if attempt.decision.status == "accepted":
            stop_reason = (
                "Measured improvement passes the fresh challenge and correctness guardrail."
            )
            break
        if number == MAX_ATTEMPTS:
            break
        try:
            revised = await reasoner.propose(attempts)
        except ValueError:
            stop_reason = (
                "Revision unavailable. Recorded measurements are retained; "
                "no accepted candidate is claimed."
            )
            break
        if any(a.proposal.cache_fields == revised.cache_fields for a in attempts):
            stop_reason = (
                "Model repeated a tested configuration. Stopped without wasting another attempt."
            )
            break
        proposal = revised
    control = measure(
        Proposal(
            cache_fields=["sku"],
            rationale="Declared unsafe negative control; not a model proposal.",
        ),
        saved["seed"],
        0,
    )
    report: dict[str, object] = {
        "schema_version": 1,
        "plan": body.plan.model_dump(mode="json"),
        "challenge_seed_reveal": saved["seed"],
        "negative_control": control.model_dump(mode="json"),
        "attempts": [a.model_dump(mode="json") for a in attempts],
        "winner_attempt": next(
            (a.number for a in attempts if a.decision.status == "accepted"), None
        ),
        "stop_reason": stop_reason,
        "model_calls": saved["model_calls"] + reasoner.calls,
        "model_tokens": saved["model_tokens"] + reasoner.tokens,
        "limitations": [
            "Synthetic pricing workload; no production latency or cloud-cost claim.",
            "Work units count reference function calls. Timings are not the objective.",
            "Fresh generated challenge per attempt; previous failures inform revisions.",
            "Three deterministic rounds check reproducibility, not statistical significance.",
            "Fixed configuration search over three fields; not arbitrary code generation.",
            "Capsule hash verifies consistency, not authenticity or benchmark completeness.",
            "Ephemeral host storage can reset quotas and history; export evidence before restart.",
        ],
    }
    report["capsule_sha256"] = digest(report)
    storage.finish(body.plan.run_id, report)
    evidence.append(
        body.plan.run_id,
        EvidenceRecord(
            id=f"{body.plan.run_id}:report",
            kind=EvidenceKind.TOOL_OUTPUT,
            claim="Completed bounded campaign; evidence capsule persisted.",
            source=PROTOCOL,
            content_hash=str(report["capsule_sha256"]),
            metadata={"capsule_json": json.dumps(report)},
        ),
    )
    return report
