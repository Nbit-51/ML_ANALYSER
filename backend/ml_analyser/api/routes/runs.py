"""Read-only analysis preview endpoints."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import Field

from ml_analyser.adapters.ml_threshold import AdapterValidationError
from ml_analyser.agent.evaluator import DecisionEvaluator
from ml_analyser.agent.ml_demo import ThresholdDemoResult, ThresholdDemoService
from ml_analyser.agent.models import PreviewRunResult, StrictModel, SuccessContract
from ml_analyser.agent.orchestrator import PreviewOrchestrator
from ml_analyser.agent.providers import DeterministicMockProvider
from ml_analyser.core.config import get_settings
from ml_analyser.core.workspace import InvalidWorkspacePath, resolve_project_path
from ml_analyser.persistence import SQLiteRunStore
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
    orchestrator = PreviewOrchestrator(
        provider=DeterministicMockProvider(),
        inspector=RepositoryInventoryTool(),
    )
    try:
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

    service = ThresholdDemoService(
        provider=DeterministicMockProvider(),
        inspector=RepositoryInventoryTool(),
        evaluator=DecisionEvaluator(),
        store=SQLiteRunStore(settings.state_database),
    )
    try:
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
