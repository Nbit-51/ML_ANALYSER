"""Tests for the initial service endpoints."""

from fastapi.testclient import TestClient

from ml_analyser import __version__
from ml_analyser.main import app

client = TestClient(app)


def test_service_root() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "name": "ML Analyser API",
        "status": "ok",
        "docs": "/docs",
    }


def test_health_check() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "ML Analyser API",
        "version": __version__,
        "environment": "development",
    }
