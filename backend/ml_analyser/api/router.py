"""Top-level API router."""

from fastapi import APIRouter

from ml_analyser.api.routes.benchmarks import router as benchmarks_router
from ml_analyser.api.routes.health import router as health_router
from ml_analyser.api.routes.runs import router as runs_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(runs_router)
api_router.include_router(benchmarks_router)
