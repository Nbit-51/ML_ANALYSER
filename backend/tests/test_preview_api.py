"""API tests for safe workspace-bound preview runs."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ml_analyser.core.config import get_settings
from ml_analyser.main import app

client = TestClient(app)


def _preview_payload(project_path: str) -> dict[str, object]:
    return {
        "project_path": project_path,
        "success_contract": {
            "objective": {
                "metric": "p95_latency_ms",
                "direction": "minimize",
                "target": 250,
            },
            "constraints": [
                {
                    "metric": "tests_pass_rate",
                    "operator": "eq",
                    "threshold": 1.0,
                }
            ],
            "budget": {"max_wall_clock_seconds": 300, "max_experiments": 3},
        },
    }


def test_preview_endpoint_returns_structured_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "sample-api"
    project.mkdir()
    (project / "app.py").write_text("print('hello')\n", encoding="utf-8")

    monkeypatch.setenv("ML_ANALYSER_WORKSPACE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    try:
        response = client.post("/api/v1/runs/preview", json=_preview_payload("sample-api"))
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    body = response.json()
    assert body["final_state"] == "completed"
    assert body["provider"] == "deterministic-local"
    assert body["inventory"]["total_files"] == 1
    assert body["hypotheses"][0]["kind"] == "baseline"
    assert body["experiments"][0]["command"] is None


def test_preview_endpoint_rejects_workspace_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ML_ANALYSER_WORKSPACE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    try:
        response = client.post("/api/v1/runs/preview", json=_preview_payload("../outside"))
    finally:
        get_settings.cache_clear()

    assert response.status_code in {400, 404}
