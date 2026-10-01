"""Repository intake and authentication boundaries, including real account isolation."""

import base64
import gzip
import io
import tarfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ml_analyser.api.routes import auth
from ml_analyser.core.auth import AuthStore, account_settings
from ml_analyser.core.config import Settings, get_settings, request_settings
from ml_analyser.main import app
from ml_analyser.tools import import_repository as intake


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ML_ANALYSER_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    monkeypatch.setenv("ML_ANALYSER_AUTH_DATABASE", str(tmp_path / "auth.db"))
    monkeypatch.setenv("ML_ANALYSER_STATE_DATABASE", str(tmp_path / "runs.db"))
    get_settings.cache_clear()
    return TestClient(app)


def file_data(path: str, content: bytes = b"print('hello')") -> dict[str, str]:
    return {"path": path, "content": base64.b64encode(content).decode()}


def enable_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ML_ANALYSER_GITHUB_CLIENT_ID", "test-id")
    monkeypatch.setenv("ML_ANALYSER_GITHUB_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("ML_ANALYSER_GITHUB_ALLOWED_USERS", "alice,bob")
    get_settings.cache_clear()


def test_landing_login_and_setup(client: TestClient) -> None:
    assert "A proven improvement?" in client.get("/").text
    assert "Connect your GitHub OAuth app" in client.get("/login").text
    assert "My repository" in client.get("/app").text
    status = client.get("/api/v1/auth/status").json()
    assert status["configured"] is False and status["user"] is None
    assert (
        client.get("/api/v1/auth/github", follow_redirects=False).headers["location"]
        == "/login?setup=required"
    )


def test_folder_import_and_preview(client: TestClient) -> None:
    result = client.post(
        "/api/v1/repositories/folder",
        json={
            "files": [
                file_data("main.py"),
                file_data(".env", b"private"),
                file_data("node_modules/a.js"),
            ]
        },
    )
    assert result.status_code == 201, result.text
    data = result.json()
    root = get_settings().workspace_root / data["project_path"]
    assert data["files"] == 1 and data["skipped"] == 2
    assert (root / "main.py").read_bytes() == b"print('hello')"
    assert not (root / ".env").exists()
    preview = client.post(
        "/api/v1/runs/preview",
        json={
            "project_path": data["project_path"],
            "success_contract": {"objective": {"metric": "duration", "direction": "minimize"}},
        },
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["inventory"]["total_files"] == 1


@pytest.mark.parametrize(
    "name",
    [
        "../outside.py",
        "/etc/passwd",
        "C:/secret",
        "a/../b",
        "a\\b",
        "a//b",
        "NUL.txt",
        "a.",
        "a/CON",
        "a:ads",
    ],
)
def test_unsafe_upload_paths(client: TestClient, name: str) -> None:
    response = client.post("/api/v1/repositories/folder", json={"files": [file_data(name)]})
    assert response.status_code == 422
    assert not get_settings().workspace_root.exists()


def test_upload_limits_duplicates_encoding_and_empty(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    for files in (
        [file_data("a.py"), file_data("A.py")],
        [file_data(".env")],
        [{"path": "a.py", "content": "!invalid!"}],
        [],
    ):
        assert client.post("/api/v1/repositories/folder", json={"files": files}).status_code == 422
    monkeypatch.setattr(intake, "MAX_FILE_BYTES", 3)
    assert (
        client.post(
            "/api/v1/repositories/folder", json={"files": [file_data("big.py")]}
        ).status_code
        == 422
    )
    monkeypatch.setattr("ml_analyser.core.access.MAX_REQUEST_BYTES", 10)
    assert client.post("/api/v1/repositories/folder", content=b"x" * 11).status_code == 413
    with pytest.raises(ValueError):
        intake.save_files(get_settings().workspace_root, [])


def archive_bytes(name: str = "repo/main.py", kind: bytes = tarfile.REGTYPE) -> bytes:
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as archive:
        info = tarfile.TarInfo("repo")
        info.type = tarfile.DIRTYPE
        archive.addfile(info)
        info = tarfile.TarInfo(name)
        info.type = kind
        info.size = 8 if kind == tarfile.REGTYPE else 0
        archive.addfile(info, io.BytesIO(b"print(1)"))
    return data.getvalue()


def mock_download(monkeypatch: pytest.MonkeyPatch, data: bytes, status: int = 200) -> None:
    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "codeload.github.com"
        return httpx.Response(status, content=data)

    monkeypatch.setattr(
        intake.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )


def test_github_import(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_download(monkeypatch, archive_bytes())
    response = client.post(
        "/api/v1/repositories/github", json={"url": "https://github.com/owner/repo.git"}
    )
    assert response.status_code == 201, response.text
    assert (get_settings().workspace_root / response.json()["project_path"] / "main.py").exists()


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/o/r",
        "https://localhost/o/r",
        "https://github.com@evil.test/o/r",
        "https://github.com/o/r/tree/main",
        "https://github.com/o/r?q=x",
        "https://github.com/o/..",
    ],
)
def test_github_url_boundary(url: str) -> None:
    with pytest.raises(ValueError):
        intake.github_archive(url)


@pytest.mark.parametrize(
    "name,kind",
    [
        ("repo/../escape", tarfile.REGTYPE),
        ("repo/link", tarfile.SYMTYPE),
        ("repo/pipe", tarfile.FIFOTYPE),
    ],
)
def test_archive_paths_and_special_files(
    monkeypatch: pytest.MonkeyPatch, name: str, kind: bytes
) -> None:
    mock_download(monkeypatch, archive_bytes(name, kind))
    with pytest.raises(ValueError):
        intake.github_archive("https://github.com/owner/repo")


def test_archive_status_and_bomb(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    with monkeypatch.context() as patch:
        mock_download(patch, b"not found", 404)
        assert (
            client.post(
                "/api/v1/repositories/github", json={"url": "https://github.com/o/r"}
            ).status_code
            == 422
        )
    with monkeypatch.context() as patch:
        mock_download(patch, gzip.compress(b"x" * 20000))
        patch.setattr(intake, "MAX_BYTES", 1000)
        with pytest.raises(ValueError, match="Expanded"):
            intake.github_archive("https://github.com/o/r")
    with monkeypatch.context() as patch:
        mock_download(patch, b"x" * 100)
        patch.setattr(intake, "MAX_BYTES", 50)
        with pytest.raises(ValueError, match="archive exceeds"):
            intake.github_archive("https://github.com/o/r")


def test_origins_and_host(client: TestClient) -> None:
    assert (
        client.post("/api/v1/auth/logout", headers={"Origin": "https://evil.test"}).status_code
        == 403
    )
    assert (
        client.post("/api/v1/auth/logout", headers={"Sec-Fetch-Site": "cross-site"}).status_code
        == 403
    )
    assert client.get("/", headers={"Host": "attacker.test"}).status_code == 400
    assert (
        client.post("/api/v1/auth/logout", headers={"Origin": "http://testserver"}).status_code
        == 200
    )


def test_session_state_expiry_revocation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = AuthStore(tmp_path / "auth.db")
    state, verifier = store.begin()
    assert store.consume(state) == verifier
    assert store.consume(state) is None
    token = store.create("123", "alice")
    assert store.user(token) == {"id": "123", "login": "alice"}
    store.revoke(token)
    assert store.user(token) is None
    token = store.create("123", "alice")
    state, _ = store.begin()
    monkeypatch.setattr("ml_analyser.core.auth.time.time", lambda: 10**12)
    assert store.consume(state) is None and store.user(token) is None
    with pytest.raises(ValueError):
        account_settings(get_settings(), "../bad")


def test_oauth_state_and_account_isolation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_auth(monkeypatch)
    assert client.get("/app", follow_redirects=False).headers["location"] == "/login"
    assert (
        client.post("/api/v1/repositories/folder", json={"files": [file_data("a.py")]}).status_code
        == 401
    )
    response = client.get("/api/v1/auth/github", follow_redirects=False)
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert "scope" not in query
    assert "httponly" in response.headers["set-cookie"].lower()
    assert client.get("/api/v1/auth/callback?state=wrong&code=test").status_code == 400

    async def identity(code: str, verifier: str) -> dict[str, object]:
        assert code == "test" and len(verifier) >= 43
        return {"id": 123, "login": "alice"}

    monkeypatch.setattr(auth, "github_identity", identity)
    callback = client.get(
        "/api/v1/auth/callback",
        params={"state": query["state"][0], "code": "test"},
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert client.get("/api/v1/auth/status").json()["user"]["login"] == "alice"
    assert (
        client.get(
            "/api/v1/auth/callback", params={"state": query["state"][0], "code": "test"}
        ).status_code
        == 400
    )
    result = client.post("/api/v1/repositories/folder", json={"files": [file_data("a.py")]})
    path = result.json()["project_path"]
    alice = account_settings(get_settings(), "123")
    assert (alice.workspace_root / path / "a.py").exists()
    store = AuthStore(get_settings().auth_database)
    client.cookies.set("ml_session", store.create("456", "bob"), domain="testserver.local")
    other = client.post(
        "/api/v1/runs/preview",
        json={
            "project_path": path,
            "success_contract": {"objective": {"metric": "f1", "direction": "maximize"}},
        },
    )
    assert other.status_code == 404
    assert request_settings.get() is None
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/status").json()["user"] is None


@pytest.mark.parametrize(
    "identity,status",
    [
        ({"id": 99, "login": "outsider"}, 403),
        ({"login": "alice"}, 502),
        ({"id": "../x", "login": "alice"}, 502),
    ],
)
def test_oauth_rejects_unapproved_and_invalid_identity(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, identity: dict[str, object], status: int
) -> None:
    enable_auth(monkeypatch)

    async def fake_identity(code: str, verifier: str) -> dict[str, object]:
        return identity

    monkeypatch.setattr(auth, "github_identity", fake_identity)
    response = client.get("/api/v1/auth/github", follow_redirects=False)
    state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
    result = client.get("/api/v1/auth/callback", params={"code": "test", "state": state})
    assert result.status_code == status
    assert client.get("/api/v1/auth/status").json()["user"] is None


def test_partial_configuration_fails_closed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ML_ANALYSER_GITHUB_CLIENT_ID", "only-id")
    get_settings.cache_clear()
    assert client.get("/api/v1/auth/status").json()["enabled"] is True
    assert client.get("/app", follow_redirects=False).status_code == 303


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.test",
        "https://user:password@host.test",
        "https://host.test/path",
        "file:///tmp",
    ],
)
def test_callback_origin_validation(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(app_url=url)


@pytest.mark.parametrize("valid", [True, False])
def test_github_exchange_protocol(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, valid: bool
) -> None:
    import asyncio

    enable_auth(monkeypatch)
    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("access_token"):
            assert b"code_verifier=verifier" in request.content
            return httpx.Response(200, json={"access_token": "ephemeral"} if valid else {})
        assert request.headers["Authorization"] == "Bearer ephemeral"
        return httpx.Response(200, json={"id": 123, "login": "alice"})

    monkeypatch.setattr(
        auth.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    if valid:
        assert asyncio.run(auth.github_identity("code", "verifier"))["id"] == 123
    else:
        with pytest.raises(ValueError):
            asyncio.run(auth.github_identity("code", "verifier"))
