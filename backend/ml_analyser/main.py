"""FastAPI application entry point."""

from fastapi import FastAPI

from ml_analyser import __version__
from ml_analyser.api.router import api_router
from ml_analyser.core.config import get_settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="API for the evidence-driven ML Analyser agent.",
    )
    application.include_router(api_router, prefix=settings.api_v1_prefix)

    @application.get("/", tags=["service"])
    async def service_root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "status": "ok",
            "docs": application.docs_url or "/docs",
        }

    return application


app = create_app()
