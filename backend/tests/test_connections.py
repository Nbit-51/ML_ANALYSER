"""Hosted connection readiness, OAuth failures and imported classifier evaluation."""

import io
import json
import tarfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from ml_analyser.api.routes import auth
from ml_analyser.core.auth import account_settings
from ml_analyser.core.config import Settings, get_settings
from ml_analyser.core.connections import connection_summary
from ml_analyser.main import app
from ml_analyser.tools import import_repository as intake


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ML_ANALYSER_APP_URL", "https://ml-analyser.onrender.com")
    monkeypatch.setenv("ML_ANALYSER_DEPLOYMENT_MODE", "judge")
    monkeypatch.setenv("ML_ANALYSER_AUTH_DATABASE", str(tmp_path / "auth.db"))
    monkeypatch.setenv("ML_ANALYSER_STATE_DATABASE", str(tmp_path / "runs.db"))
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("NEBIUS_MODEL", "")
    get_settings.cache_clear()
    return TestClient(app, base_url="https://ml-analyser.onrender.com")


def configure_github(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ML_ANALYSER_GITHUB_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("ML_ANALYSER_GITHUB_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("ML_ANALYSER_GITHUB_ALLOWED_USERS", "owner")
    get_settings.cache_clear()


def sign_in(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    configure_github(monkeypatch)

    async def identity(code: str, verifier: str) -> dict[str, object]:
        assert code == "single-use-code" and len(verifier) >= 43
        return {"id": 123, "login": "owner"}

    monkeypatch.setattr(auth, "github_identity", identity)
    start = client.get("/api/v1/auth/github", follow_redirects=False)
    assert "secure" in start.headers["set-cookie"].lower()
    query = parse_qs(urlsplit(start.headers["location"]).query)
    result = client.get(
        "/api/v1/auth/callback",
        params={
            "code": "single-use-code",
            "state": query["state"][0],
        },
        follow_redirects=False,
    )
    assert result.status_code == 303 and result.headers["location"] == "/app"
    assert "secure" in result.headers["set-cookie"].lower()
    assert client.get("/api/v1/auth/status").json()["user"]["login"] == "owner"


def test_hosted_setup_fails_closed_without_local_demo(client: TestClient) -> None:
    state = client.get("/api/v1/auth/status").json()
    assert state["local_demo_available"] is False
    assert state["app_url"] == "https://ml-analyser.onrender.com"
    assert state["callback_url"] == state["app_url"] + "/api/v1/auth/callback"
    assert client.get("/app", follow_redirects=False).headers["location"] == "/login"
    assert (
        client.post(
            "/api/v1/repositories/github", json={"url": "https://github.com/o/r"}
        ).status_code
        == 403
    )
    response = client.get("/api/v1/connections")
    assert response.status_code == 200
    data = response.json()
    assert data["github"]["status"] == "not_configured"
    assert data["nebius"]["status"] == "not_configured"
    assert data["github"]["verification"] == "not_tested"
    assert data["settings_location"] == "host environment settings"


def test_connection_status_never_serializes_credentials(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_github(monkeypatch)
    monkeypatch.setenv("ML_ANALYSER_MODEL_PROVIDER", "nebius")
    monkeypatch.setenv("NEBIUS_API_KEY", "private-test-key-do-not-expose")
    monkeypatch.setenv("NEBIUS_MODEL", "nvidia/test")
    monkeypatch.setenv("ML_ANALYSER_LAB_DAILY_LIMIT", "2")
    get_settings.cache_clear()
    response = client.get("/api/v1/connections")
    assert "private-test-key-do-not-expose" not in response.text
    assert "test-client-secret" not in response.text
    assert "test-client-id" not in response.text
    assert response.json()["github"]["status"] == "configured"
    assert response.json()["nebius"]["status"] == "configured"
    assert response.json()["nebius"]["verification"] == "not_tested"
    assert response.json()["live_lab_enabled"] is True


def test_partial_disabled_and_empty_allowlist_states() -> None:
    settings = Settings(
        _env_file=None,
        model_provider="mock",
        NEBIUS_API_KEY="test-key",
        NEBIUS_MODEL="test-model",
        github_client_id="id",
        github_client_secret="secret",
        github_allowed_users=" , , ",
    )
    assert settings.auth_ready is False
    assert settings.github_allowed_logins == set()
    status = connection_summary(settings)
    assert status.github.status == "incomplete"
    assert status.github.missing_settings == ["ML_ANALYSER_GITHUB_ALLOWED_USERS"]
    assert status.nebius.status == "disabled"
    assert not status.live_lab_enabled
    settings = settings.model_copy(
        update={
            "github_client_id": " ",
            "github_client_secret": auth.get_settings().github_client_secret,
        }
    )
    assert settings.auth_ready is False


@pytest.mark.parametrize(
    "identity",
    [
        {"id": True, "login": "owner"},
        {"id": 0, "login": "owner"},
        {"id": "123", "login": "owner"},
        {"id": 123, "login": "../owner"},
        {"id": 123, "login": ""},
        {"id": 123, "login": None},
    ],
)
def test_invalid_github_identity_cannot_create_session(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    identity: dict[str, object],
) -> None:
    configure_github(monkeypatch)

    async def invalid(code: str, verifier: str) -> dict[str, object]:
        return identity

    monkeypatch.setattr(auth, "github_identity", invalid)
    start = client.get("/api/v1/auth/github", follow_redirects=False)
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    response = client.get("/api/v1/auth/callback", params={"state": state, "code": "test"})
    assert response.status_code == 502
    assert client.get("/api/v1/auth/status").json()["user"] is None


def test_imported_nested_classifier_runs_and_saves_measured_f1(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sign_in(client, monkeypatch)
    seeded = account_settings(get_settings(), "123").workspace_root
    assert (seeded / "ml-training-demo" / "train.csv").is_file()
    assert (seeded / "ml-regression-demo" / "train.py").is_file()
    source = Path(__file__).resolve().parents[2] / "workspaces/ml-training-demo"
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as tar:
        for file in source.iterdir():
            if not file.is_file() or file.suffix == ".pyc":
                continue
            data = file.read_bytes()
            info = tarfile.TarInfo("repo/evaluation/classifier/" + file.name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    real_client = httpx.Client
    monkeypatch.setattr(
        intake.httpx,
        "Client",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=archive.getvalue())
            ),
            **kwargs,
        ),
    )
    imported = client.post(
        "/api/v1/repositories/github", json={"url": "https://github.com/owner/classifier"}
    )
    assert imported.status_code == 201, imported.text
    project = imported.json()["project_path"]
    details = client.get("/api/v1/repositories/details", params={"project_path": project}).json()
    assert details["executed"] is False
    nested = details["benchmark_projects"][0]["project_path"]
    assert nested == project + "/evaluation/classifier"
    definition = client.get("/api/v1/repositories/details", params={"project_path": nested}).json()
    f1 = next(
        metric
        for metric in definition["adapters"][0]["measurement_definitions"]
        if metric["name"] == "f1"
    )
    assert f1["direction"] == "maximize" and f1["unit"] == "ratio"
    root = seeded / nested
    before = {file.name: file.read_bytes() for file in root.iterdir() if file.is_file()}
    request = json.loads((source / "prepare_request.json").read_text())
    request.update(adapter="ml_training", project_path=nested, project_id="imported-classifier")
    prepared = client.post("/api/v1/runs/prepare", json=request)
    assert prepared.status_code == 201, prepared.text
    data = prepared.json()
    approval = data["approval"]["id"]
    assert (
        client.post(f"/api/v1/runs/approvals/{approval}", json={"approved": True}).status_code
        == 200
    )
    result = client.post(
        "/api/v1/runs/execute",
        json={"adapter": "ml_training", "approval_id": approval, "plan": data["plan"]},
    )
    assert result.status_code == 200, result.text
    report = result.json()
    assert report["decision"]["status"] == "accepted"
    objective = report["decision"]["objective"]
    assert objective["metric"] == "f1"
    assert 0 <= objective["baseline_value"] < objective["candidate_value"] <= 1
    assert report["original_project_modified"] is False
    assert {file.name: file.read_bytes() for file in root.iterdir() if file.is_file()} == before
    assert client.get("/api/v1/runs/history").json()[0]["metric"] == "f1"
    assert client.get(f"/api/v1/runs/{report['run_id']}/report").json() == report


def test_nested_discovery_is_bounded_and_ignores_invalid_manifests(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(client, monkeypatch)
    workspace = account_settings(get_settings(), "123").workspace_root
    root = workspace / "many"
    source = Path(__file__).resolve().parents[2] / "workspaces/ml-regression-demo"
    import shutil

    for number in range(16):
        shutil.copytree(source, root / f"evaluation-{number:02}")
    (root / "broken").mkdir()
    (root / "broken/ml_experiment.json").write_text("{}")
    response = client.get("/api/v1/repositories/details", params={"project_path": "many"})
    assert response.status_code == 200, response.text
    projects = response.json()["benchmark_projects"]
    assert len(projects) <= 12
    assert all(project["project_path"].startswith("many/evaluation-") for project in projects)
