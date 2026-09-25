"""One registered preparation/execution API for every supported adapter."""

import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import Field

from ml_analyser.adapters.registry import default_registry
from ml_analyser.agent.analytics import WorkbenchResult, persist_workbench_result, read_report
from ml_analyser.agent.approval import ApprovalService
from ml_analyser.agent.backend_benchmark import BackendBenchmarkPlan
from ml_analyser.agent.evaluator import DecisionEvaluator
from ml_analyser.agent.ml_training import MlTrainingPlan
from ml_analyser.agent.models import (
    ApprovalRecord,
    EvidenceRecord,
    ProjectStateGraph,
    RepositoryInventory,
    RepositorySummary,
    RunState,
    StrictModel,
    SuccessContract,
)
from ml_analyser.agent.process_benchmark import ProcessPlan
from ml_analyser.agent.providers import build_model_provider
from ml_analyser.core.config import get_settings
from ml_analyser.core.workspace import resolve_project_path
from ml_analyser.execution.workspace import IsolatedWorkspaceManager
from ml_analyser.persistence.sqlite import InvalidApprovalTransitionError, SQLiteRunStore
from ml_analyser.tools.capabilities import detect_capabilities
from ml_analyser.tools.repository import RepositoryInventoryTool

router = APIRouter(prefix="/runs", tags=["benchmarks"])


class PrepareRequest(StrictModel):
    adapter: str
    project_path: str = Field(min_length=1, max_length=500)
    project_id: str | None = None
    success_contract: SuccessContract


class ExecuteRequest(StrictModel):
    adapter: str
    approval_id: str
    plan: BackendBenchmarkPlan | MlTrainingPlan | ProcessPlan


class PrepareResult(StrictModel):
    adapter: str
    plan: BackendBenchmarkPlan | MlTrainingPlan | ProcessPlan
    approval: ApprovalRecord
    inventory: RepositoryInventory
    state_graph: ProjectStateGraph
    evidence: list[EvidenceRecord]
    repository_summary: RepositorySummary
    warnings: list[str] = Field(default_factory=list)


def pipeline_for(adapter: str) -> Any:
    settings = get_settings()
    store = SQLiteRunStore(settings.state_database)
    return (
        default_registry()
        .get(adapter)
        .pipeline(
            provider=build_model_provider(settings),
            inspector=RepositoryInventoryTool(),
            approvals=ApprovalService(store),
            evaluator=DecisionEvaluator(),
            workspaces=IsolatedWorkspaceManager(settings.execution_root),
            store=store,
        )
    )


@router.post("/prepare", status_code=201, response_model=PrepareResult)
async def prepare(request: PrepareRequest) -> PrepareResult:
    try:
        root = resolve_project_path(get_settings().workspace_root, request.project_path)
        prepared = await pipeline_for(request.adapter).prepare(
            project_id=request.project_id or Path(request.project_path).name,
            project_path=request.project_path,
            project_root=root,
            success_contract=request.success_contract,
        )
        summary, detected_evidence = detect_capabilities(prepared.inventory)
        store = SQLiteRunStore(get_settings().state_database)
        for record in detected_evidence:
            store.append(prepared.plan.run_id, record)
        summary.adapters = default_registry().describe(root)
        return PrepareResult.model_validate(
            {
                **prepared.model_dump(mode="json"),
                "evidence": [*prepared.evidence, *detected_evidence],
                "repository_summary": summary.model_dump(mode="json"),
                "adapter": request.adapter,
            }
        )
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def execute_registered(request: ExecuteRequest, *, background: bool = False) -> WorkbenchResult:
    settings = get_settings()
    store = SQLiteRunStore(settings.state_database)
    registration = default_registry().get(request.adapter)
    plan: Any = registration.plan_model.model_validate(request.plan.model_dump())
    root = resolve_project_path(settings.workspace_root, plan.project_path)
    summary, _ = detect_capabilities(RepositoryInventoryTool().inspect(str(root)))
    summary.adapters = default_registry().describe(root)

    def progress(state: RunState) -> None:
        store.record_run_state(plan.run_id, state.value)

    result = pipeline_for(request.adapter).execute(
        plan=plan,
        approval_id=request.approval_id,
        project_root=root,
        on_state=progress if background else None,
    )
    return persist_workbench_result(
        store, request.adapter, result, plan, registration.normalize(result, plan), summary
    )


@router.post("/execute", response_model=WorkbenchResult)
async def execute(request: ExecuteRequest) -> WorkbenchResult:
    try:
        return execute_registered(request)
    except InvalidApprovalTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def background_execute(request: ExecuteRequest, run_id: str) -> None:
    store = SQLiteRunStore(get_settings().state_database)
    try:
        result = execute_registered(request, background=True)
        store.finish_live_run(run_id, result.model_dump(mode="json"))
    except Exception as error:
        store.fail_live_run(run_id, f"{type(error).__name__}: {error}")


@router.post("/start", status_code=202)
async def start(request: ExecuteRequest, tasks: BackgroundTasks) -> dict[str, str]:
    from ml_analyser.api.routes.runs import _validate_ready_approval

    try:
        registration = default_registry().get(request.adapter)
        plan: Any = registration.plan_model.model_validate(request.plan.model_dump())
        store = SQLiteRunStore(get_settings().state_database)
        _validate_ready_approval(store, request.approval_id, plan)
        store.create_live_run(plan.run_id, request.adapter)
        tasks.add_task(background_execute, request, plan.run_id)
        return {"run_id": plan.run_id, "status": "queued"}
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="Run is already queued.") from error
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/{run_id}/report", response_model=WorkbenchResult)
async def report(run_id: str) -> WorkbenchResult:
    try:
        return read_report(SQLiteRunStore(get_settings().state_database), run_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
