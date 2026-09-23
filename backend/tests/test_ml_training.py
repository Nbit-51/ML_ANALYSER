"""End-to-end training experiment and live run tests."""

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ml_analyser.adapters.ml_training import MlTrainingAdapter, MlTrainingError
from ml_analyser.core.config import get_settings
from ml_analyser.main import app

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "workspaces" / "ml-training-demo"
CLIENT = TestClient(app)


def _configure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    shutil.copytree(SOURCE, tmp_path / "demo")
    monkeypatch.setenv("ML_ANALYSER_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("ML_ANALYSER_EXECUTION_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("ML_ANALYSER_STATE_DATABASE", str(tmp_path / "state.db"))
    get_settings.cache_clear()
    payload = json.loads((SOURCE / "prepare_request.json").read_text(encoding="utf-8"))
    payload["project_path"] = "demo"
    return payload


def test_training_run_measures_real_improvement_and_retains_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _configure(tmp_path, monkeypatch)
    try:
        prepared_response = CLIENT.post("/api/v1/runs/ml-training/prepare", json=payload)
        assert prepared_response.status_code == 201
        prepared = prepared_response.json()
        approval_id = prepared["approval"]["id"]
        assert (
            CLIENT.post(
                f"/api/v1/runs/approvals/{approval_id}", json={"approved": True}
            ).status_code
            == 200
        )
        execution = CLIENT.post(
            "/api/v1/runs/ml-training/execute",
            json={"approval_id": approval_id, "plan": prepared["plan"]},
        )
        assert execution.status_code == 200
        result = execution.json()
        assert result["baseline"]["metrics"]["f1"] == pytest.approx(2 / 3)
        assert result["candidate"]["metrics"]["f1"] == 1.0
        assert result["decision"]["status"] == "accepted"
        assert result["disposition"] == "retained"
        assert result["original_project_modified"] is False
        assert json.loads((tmp_path / "demo" / "config.json").read_text())["epochs"] == 1
        assert Path(result["retained_candidate_workspace"]).is_dir()
        assert (
            CLIENT.post(
                "/api/v1/runs/ml-training/execute",
                json={"approval_id": approval_id, "plan": prepared["plan"]},
            ).status_code
            == 409
        )
    finally:
        get_settings.cache_clear()


def test_live_run_persists_events_and_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _configure(tmp_path, monkeypatch)
    try:
        prepared = CLIENT.post("/api/v1/runs/ml-training/prepare", json=payload).json()
        approval_id = prepared["approval"]["id"]
        CLIENT.post(f"/api/v1/runs/approvals/{approval_id}", json={"approved": True})
        started = CLIENT.post(
            "/api/v1/runs/ml-training/start",
            json={"approval_id": approval_id, "plan": prepared["plan"]},
        )
        assert started.status_code == 202
        run_id = started.json()["run_id"]
        snapshot = CLIENT.get(f"/api/v1/runs/live/{run_id}")
        assert snapshot.status_code == 200
        data = snapshot.json()
        assert data["status"] == "completed"
        assert "executing" in data["events"]
        assert "measuring" in data["events"]
        assert data["result"]["decision"]["status"] == "accepted"
        assert (
            CLIENT.post(
                "/api/v1/runs/ml-training/start",
                json={"approval_id": approval_id, "plan": prepared["plan"]},
            ).status_code
            == 409
        )
    finally:
        get_settings.cache_clear()


def test_training_source_change_invalidates_approved_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _configure(tmp_path, monkeypatch)
    try:
        prepared = CLIENT.post("/api/v1/runs/ml-training/prepare", json=payload).json()
        approval_id = prepared["approval"]["id"]
        CLIENT.post(f"/api/v1/runs/approvals/{approval_id}", json={"approved": True})
        (tmp_path / "demo" / "config.json").write_text(
            '{"epochs": 2, "learning_rate": 0.0001}', encoding="utf-8"
        )
        result = CLIENT.post(
            "/api/v1/runs/ml-training/execute",
            json={"approval_id": approval_id, "plan": prepared["plan"]},
        )
        assert result.status_code == 422
        assert "changed after preparation" in result.json()["detail"]
    finally:
        get_settings.cache_clear()


def test_training_adapter_rejects_undeclared_config_key(tmp_path: Path) -> None:
    project = tmp_path / "demo"
    shutil.copytree(SOURCE, project)
    manifest_path = project / "ml_experiment.json"
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_data["candidate_overrides"] = {"unknown_parameter": 10}
    manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")
    adapter = MlTrainingAdapter()
    manifest = adapter.load_manifest(project)

    with pytest.raises(MlTrainingError, match="existing config keys"):
        adapter.apply_candidate(project, manifest)


def test_training_adapter_rejects_missing_entrypoint_and_escaping_output(tmp_path: Path) -> None:
    project = tmp_path / "demo"
    shutil.copytree(SOURCE, project)
    manifest_path = project / "ml_experiment.json"
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_data["entrypoint"] = "missing.py"
    manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")
    adapter = MlTrainingAdapter()
    with pytest.raises(MlTrainingError, match="declared input file"):
        adapter.load_manifest(project)

    manifest_data["entrypoint"] = "train.py"
    manifest_data["metrics_file"] = "../escaped.json"
    manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")
    with pytest.raises(MlTrainingError, match="root-level"):
        adapter.load_manifest(project)


def test_training_adapter_rejects_failed_or_invalid_measurement(tmp_path: Path) -> None:
    project = tmp_path / "demo"
    shutil.copytree(SOURCE, project)
    adapter = MlTrainingAdapter()
    manifest = adapter.load_manifest(project)
    script = project / "train.py"

    script.write_text("raise RuntimeError('intentional failure')\n", encoding="utf-8")
    with pytest.raises(MlTrainingError, match="training exited"):
        adapter.measure(project, manifest)

    script.write_text("print('no metrics')\n", encoding="utf-8")
    with pytest.raises(MlTrainingError, match="did not produce valid metrics"):
        adapter.measure(project, manifest)


def test_unknown_live_run_is_not_found() -> None:
    assert CLIENT.get("/api/v1/runs/live/not-a-run").status_code == 404


def test_live_backend_benchmark_uses_same_persisted_timeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend_source = ROOT / "workspaces" / "backend-benchmark-demo"
    shutil.copytree(backend_source, tmp_path / "backend-demo")
    monkeypatch.setenv("ML_ANALYSER_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("ML_ANALYSER_EXECUTION_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("ML_ANALYSER_STATE_DATABASE", str(tmp_path / "state.db"))
    get_settings.cache_clear()
    payload = json.loads((backend_source / "prepare_request.json").read_text(encoding="utf-8"))
    payload["project_path"] = "backend-demo"
    try:
        prepared_response = CLIENT.post("/api/v1/runs/backend-benchmark/prepare", json=payload)
        assert prepared_response.status_code == 201
        prepared = prepared_response.json()
        approval_id = prepared["approval"]["id"]
        assert (
            CLIENT.post(
                f"/api/v1/runs/approvals/{approval_id}", json={"approved": True}
            ).status_code
            == 200
        )
        started = CLIENT.post(
            "/api/v1/runs/backend-benchmark/start",
            json={"approval_id": approval_id, "plan": prepared["plan"]},
        )
        assert started.status_code == 202
        snapshot = CLIENT.get(f"/api/v1/runs/live/{started.json()['run_id']}").json()
        assert snapshot["status"] == "completed"
        assert snapshot["result"]["decision"]["status"] == "accepted"
        assert "measuring" in snapshot["events"]
    finally:
        get_settings.cache_clear()
