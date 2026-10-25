"""Service health endpoints."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from ml_analyser import __version__
from ml_analyser.core.config import get_settings
from ml_analyser.core.connections import ConnectionSummary, connection_summary

router = APIRouter(tags=["health"])


@router.get("/connections", response_model=ConnectionSummary)
def connections() -> ConnectionSummary:
    """Report presence of required settings; never return secret values."""
    return connection_summary(get_settings())


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
