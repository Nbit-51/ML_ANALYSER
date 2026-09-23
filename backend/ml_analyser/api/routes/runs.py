"""Preview, approval, execution, and live run endpoints."""

import sqlite3
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import Field

from ml_analyser.adapters.backend_http import BackendAdapterError
from ml_analyser.adapters.ml_threshold import AdapterValidationError
from ml_analyser.adapters.ml_training import MlTrainingError
from ml_analyser.agent.approval import ApprovalService
from ml_analyser.agent.backend_benchmark import (
    BackendBenchmarkPipeline,
    BackendBenchmarkPlan,
    BackendExecutionResult,
    BackendPrepareResult,
)
from ml_analyser.agent.evaluator import DecisionEvaluator
from ml_analyser.agent.ids import model_fingerprint
from ml_analyser.agent.ml_demo import ThresholdDemoResult, ThresholdDemoService
from ml_analyser.agent.ml_training import (
    MlTrainingPipeline,
    MlTrainingPlan,
    MlTrainingPrepareResult,
    MlTrainingResult,
)
from ml_analyser.agent.models import (
    ApprovalRecord,
    ApprovalStatus,
    PreviewRunResult,
    RunState,
    StrictModel,
    SuccessContract,
)
from ml_analyser.agent.orchestrator import PreviewOrchestrator
from ml_analyser.agent.providers import (
    DeterministicMockProvider,
    ProviderConfigurationError,
    ProviderResponseError,
    build_model_provider,
)
from ml_analyser.core.config import get_settings
from ml_analyser.core.workspace import InvalidWorkspacePath, resolve_project_path
from ml_analyser.execution import IsolatedWorkspaceManager
from ml_analyser.execution.workspace import WorkspaceIsolationError
from ml_analyser.persistence import SQLiteRunStore
from ml_analyser.persistence.sqlite import (
    InvalidApprovalTransitionError,
    UnknownApprovalError,
)
from ml_analyser.tools.repository import RepositoryInventoryError, RepositoryInventoryTool

router = APIRouter(prefix="/runs", tags=["runs"])


class PreviewRunRequest(StrictModel):
    """Request a read-only analysis preview for a workspace project."""

    project_path: str = Field(min_length=1, max_length=500)
    project_id: str | None = Field(default=None, min_length=1, max_length=120)
    success_contract: SuccessContract


class ThresholdDemoRequest(PreviewRunRequest):
    """Explicitly approve the bounded, data-only threshold experiment."""

    approved: bool = False


class ApprovalDecisionRequest(StrictModel):
    approved: bool
    reason: str | None = Field(default=None, max_length=500)


class BackendExecuteRequest(StrictModel):
    approval_id: str = Field(min_length=1, max_length=120)
    plan: BackendBenchmarkPlan


class MlTrainingExecuteRequest(StrictModel):
    approval_id: str = Field(min_length=1, max_length=120)
    plan: MlTrainingPlan


def _validate_ready_approval(
    store: SQLiteRunStore,
    approval_id: str,
    plan: BackendBenchmarkPlan | MlTrainingPlan,
) -> None:
    approval = store.get_approval(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval does not exist.")
    if approval.status is not ApprovalStatus.APPROVED:
        raise HTTPException(status_code=409, detail=f"Approval is {approval.status.value}.")
    if approval.scope_fingerprint != model_fingerprint(plan):
        raise HTTPException(status_code=409, detail="Approval scope fingerprint does not match.")
    if approval.run_id != plan.run_id:
        raise HTTPException(status_code=409, detail="Approval belongs to a different run.")


def _run_background(
    *, adapter: str, plan: BackendBenchmarkPlan | MlTrainingPlan, approval_id: str
) -> None:
    settings = get_settings()
    store = SQLiteRunStore(settings.state_database)
    try:
        project_root = resolve_project_path(settings.workspace_root, plan.project_path)

        def callback(state: RunState) -> None:
            store.record_run_state(plan.run_id, state.value)

        if adapter == "backend_http" and isinstance(plan, BackendBenchmarkPlan):
            backend_result = BackendBenchmarkPipeline(
                provider=DeterministicMockProvider(),
                inspector=RepositoryInventoryTool(),
                approvals=ApprovalService(store),
                evaluator=DecisionEvaluator(),
                workspaces=IsolatedWorkspaceManager(settings.execution_root),
                store=store,
            ).execute(
                plan=plan,
                approval_id=approval_id,
                project_root=project_root,
                on_state=callback,
            )
        elif adapter == "ml_training" and isinstance(plan, MlTrainingPlan):
            ml_result = MlTrainingPipeline(
                provider=DeterministicMockProvider(),
                inspector=RepositoryInventoryTool(),
                approvals=ApprovalService(store),
                evaluator=DecisionEvaluator(),
                workspaces=IsolatedWorkspaceManager(settings.execution_root),
                store=store,
            ).execute(
                plan=plan,
                approval_id=approval_id,
                project_root=project_root,
                on_state=callback,
            )
        else:
            raise ValueError("unsupported run adapter")
        result = backend_result if adapter == "backend_http" else ml_result
        store.finish_live_run(plan.run_id, result.model_dump(mode="json"))
    except Exception as error:
        store.fail_live_run(plan.run_id, f"{type(error).__name__}: {error}")


def _queue_run(
    *,
    background_tasks: BackgroundTasks,
    adapter: str,
    plan: BackendBenchmarkPlan | MlTrainingPlan,
    approval_id: str,
) -> dict[str, str]:
    store = SQLiteRunStore(get_settings().state_database)
    _validate_ready_approval(store, approval_id, plan)
    try:
        store.create_live_run(plan.run_id, adapter)
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="Run is already queued.") from error
    background_tasks.add_task(_run_background, adapter=adapter, plan=plan, approval_id=approval_id)
    return {"run_id": plan.run_id, "status": "queued"}


@router.post(
    "/preview",
    response_model=PreviewRunResult,
    status_code=status.HTTP_200_OK,
    summary="Preview hypotheses and experiments without executing project code",
)
async def preview_run(request: PreviewRunRequest) -> PreviewRunResult:
    settings = get_settings()
    try:
        project_root = resolve_project_path(settings.workspace_root, request.project_path)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace or project path does not exist.",
        ) from error
    except InvalidWorkspacePath as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    project_id = request.project_id or Path(request.project_path).name
    try:
        orchestrator = PreviewOrchestrator(
            provider=build_model_provider(settings),
            inspector=RepositoryInventoryTool(),
        )
        return await orchestrator.preview(
            project_id=project_id,
            project_root=project_root,
            success_contract=request.success_contract,
        )
    except RepositoryInventoryError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    except ProviderConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except ProviderResponseError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error


@router.post(
    "/ml-threshold-demo",
    response_model=ThresholdDemoResult,
    status_code=status.HTTP_200_OK,
    summary="Run the approved classification-threshold demonstration",
)
async def run_ml_threshold_demo(request: ThresholdDemoRequest) -> ThresholdDemoResult:
    if not request.approved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Explicit approval is required before running the threshold experiment.",
        )

    settings = get_settings()
    try:
        project_root = resolve_project_path(settings.workspace_root, request.project_path)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace or project path does not exist.",
        ) from error
    except InvalidWorkspacePath as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    try:
        service = ThresholdDemoService(
            provider=build_model_provider(settings),
            inspector=RepositoryInventoryTool(),
            evaluator=DecisionEvaluator(),
            store=SQLiteRunStore(settings.state_database),
        )
        return await service.run(
            project_id=request.project_id or Path(request.project_path).name,
            project_root=project_root,
            success_contract=request.success_contract,
        )
    except (AdapterValidationError, RepositoryInventoryError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    except ProviderConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except ProviderResponseError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error


@router.post(
    "/backend-benchmark/prepare",
    response_model=BackendPrepareResult,
    status_code=status.HTTP_201_CREATED,
    summary="Prepare a fingerprinted backend benchmark approval request",
)
async def prepare_backend_benchmark(request: PreviewRunRequest) -> BackendPrepareResult:
    settings = get_settings()
    try:
        project_root = resolve_project_path(settings.workspace_root, request.project_path)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace or project path does not exist.",
        ) from error
    except InvalidWorkspacePath as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    try:
        store = SQLiteRunStore(settings.state_database)
        pipeline = BackendBenchmarkPipeline(
            provider=build_model_provider(settings),
            inspector=RepositoryInventoryTool(),
            approvals=ApprovalService(store),
            evaluator=DecisionEvaluator(),
            workspaces=IsolatedWorkspaceManager(settings.execution_root),
            store=store,
        )
        return await pipeline.prepare(
            project_id=request.project_id or Path(request.project_path).name,
            project_path=request.project_path,
            project_root=project_root,
            success_contract=request.success_contract,
        )
    except (BackendAdapterError, RepositoryInventoryError, WorkspaceIsolationError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    except ProviderConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except ProviderResponseError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error


@router.post(
    "/approvals/{approval_id}",
    response_model=ApprovalRecord,
    summary="Approve or reject one exact experiment scope",
)
async def decide_approval(approval_id: str, request: ApprovalDecisionRequest) -> ApprovalRecord:
    service = ApprovalService(SQLiteRunStore(get_settings().state_database))
    try:
        return service.decide(
            approval_id,
            approved=request.approved,
            reason=request.reason,
        )
    except UnknownApprovalError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except InvalidApprovalTransitionError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post(
    "/backend-benchmark/execute",
    response_model=BackendExecutionResult,
    summary="Consume approval and execute the unchanged backend benchmark plan",
)
async def execute_backend_benchmark(request: BackendExecuteRequest) -> BackendExecutionResult:
    settings = get_settings()
    try:
        project_root = resolve_project_path(settings.workspace_root, request.plan.project_path)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace or project path does not exist.",
        ) from error
    except InvalidWorkspacePath as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    store = SQLiteRunStore(settings.state_database)
    pipeline = BackendBenchmarkPipeline(
        provider=DeterministicMockProvider(),
        inspector=RepositoryInventoryTool(),
        approvals=ApprovalService(store),
        evaluator=DecisionEvaluator(),
        workspaces=IsolatedWorkspaceManager(settings.execution_root),
        store=store,
    )
    try:
        return pipeline.execute(
            plan=request.plan,
            approval_id=request.approval_id,
            project_root=project_root,
        )
    except InvalidApprovalTransitionError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except UnknownApprovalError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except (BackendAdapterError, RepositoryInventoryError, WorkspaceIsolationError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error


@router.post(
    "/ml-training/prepare",
    response_model=MlTrainingPrepareResult,
    status_code=status.HTTP_201_CREATED,
    summary="Prepare an approval-gated ML training comparison",
)
async def prepare_ml_training(request: PreviewRunRequest) -> MlTrainingPrepareResult:
    settings = get_settings()
    try:
        project_root = resolve_project_path(settings.workspace_root, request.project_path)
        store = SQLiteRunStore(settings.state_database)
        pipeline = MlTrainingPipeline(
            provider=build_model_provider(settings),
            inspector=RepositoryInventoryTool(),
            approvals=ApprovalService(store),
            evaluator=DecisionEvaluator(),
            workspaces=IsolatedWorkspaceManager(settings.execution_root),
            store=store,
        )
        return await pipeline.prepare(
            project_id=request.project_id or Path(request.project_path).name,
            project_path=request.project_path,
            project_root=project_root,
            success_contract=request.success_contract,
        )
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404, detail="Workspace or project path does not exist."
        ) from error
    except InvalidWorkspacePath as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (MlTrainingError, RepositoryInventoryError, WorkspaceIsolationError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ProviderConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ProviderResponseError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post(
    "/ml-training/execute",
    response_model=MlTrainingResult,
    summary="Consume approval and compare isolated ML training runs",
)
async def execute_ml_training(request: MlTrainingExecuteRequest) -> MlTrainingResult:
    settings = get_settings()
    try:
        project_root = resolve_project_path(settings.workspace_root, request.plan.project_path)
        store = SQLiteRunStore(settings.state_database)
        pipeline = MlTrainingPipeline(
            provider=DeterministicMockProvider(),
            inspector=RepositoryInventoryTool(),
            approvals=ApprovalService(store),
            evaluator=DecisionEvaluator(),
            workspaces=IsolatedWorkspaceManager(settings.execution_root),
            store=store,
        )
        return pipeline.execute(
            plan=request.plan, approval_id=request.approval_id, project_root=project_root
        )
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404, detail="Workspace or project path does not exist."
        ) from error
    except InvalidWorkspacePath as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except InvalidApprovalTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except UnknownApprovalError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (MlTrainingError, RepositoryInventoryError, WorkspaceIsolationError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/backend-benchmark/start", status_code=202)
async def start_backend_benchmark(
    request: BackendExecuteRequest, background_tasks: BackgroundTasks
) -> dict[str, str]:
    """Queue the exact approved backend plan and return a pollable run ID."""
    return _queue_run(
        background_tasks=background_tasks,
        adapter="backend_http",
        plan=request.plan,
        approval_id=request.approval_id,
    )


@router.post("/ml-training/start", status_code=202)
async def start_ml_training(
    request: MlTrainingExecuteRequest, background_tasks: BackgroundTasks
) -> dict[str, str]:
    """Queue the exact approved ML plan and return a pollable run ID."""
    return _queue_run(
        background_tasks=background_tasks,
        adapter="ml_training",
        plan=request.plan,
        approval_id=request.approval_id,
    )


@router.get("/live/{run_id}")
async def get_live_run(run_id: str) -> dict[str, object]:
    """Return durable stage events and the final measured result when available."""
    record = SQLiteRunStore(get_settings().state_database).get_live_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run does not exist.")
    return record
