"""Read-only analysis preview endpoints."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import Field

from ml_analyser.adapters.backend_http import BackendAdapterError
from ml_analyser.adapters.ml_threshold import AdapterValidationError
from ml_analyser.agent.approval import ApprovalService
from ml_analyser.agent.backend_benchmark import (
    BackendBenchmarkPipeline,
    BackendBenchmarkPlan,
    BackendExecutionResult,
    BackendPrepareResult,
)
from ml_analyser.agent.evaluator import DecisionEvaluator
from ml_analyser.agent.ml_demo import ThresholdDemoResult, ThresholdDemoService
from ml_analyser.agent.models import (
    ApprovalRecord,
    PreviewRunResult,
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
