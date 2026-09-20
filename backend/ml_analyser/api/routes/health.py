"""Service health endpoints."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from ml_analyser import __version__
from ml_analyser.core.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Public process health response."""

    status: Literal["ok"]
    service: str
    version: str
    environment: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return process health without calling external dependencies."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=__version__,
        environment=settings.environment,
    )
