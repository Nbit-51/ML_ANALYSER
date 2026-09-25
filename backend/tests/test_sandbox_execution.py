"""Real Linux sandbox execution; deliberately no unsandboxed fallback on other hosts."""

import json
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ml_analyser.core.config import get_settings
from ml_analyser.execution.sandbox import (
    ResourceLimits,
    SandboxError,
    run_sandbox,
    sandbox_available,
)
from ml_analyser.main import app

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(not sandbox_available(), reason="Linux bubblewrap required")


@pytest.mark.parametrize("profile", ["cli", "test_suite", "build", "microbenchmark"])
@pytest.mark.parametrize("outcome", ["accepted", "rejected", "inconclusive"])
def test_real_approved_protocol(
    profile: str, outcome: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = ROOT / "workspaces" / ("cli-benchmark-demo" if profile == "cli" else "build-test-demo")
    project = tmp_path / "project"
    shutil.copytree(source, project)
    manifest_path = project / "repo_benchmark.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["profile"] = profile
    if outcome == "rejected":
        manifest["candidate_overrides"]["incorrect"] = True
    if outcome == "inconclusive":
        manifest["repetitions"] = 1
    manifest_path.write_text(json.dumps(manifest))
    original = (project / "config.json").read_bytes()
    monkeypatch.setenv("ML_ANALYSER_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("ML_ANALYSER_EXECUTION_ROOT", str(tmp_path / "executions"))
    monkeypatch.setenv("ML_ANALYSER_STATE_DATABASE", str(tmp_path / "runs.db"))
    get_settings.cache_clear()
    client = TestClient(app)
    try:
        request = json.loads((project / "prepare_request.json").read_text())
        request["project_path"] = "project"
        prepared_response = client.post("/api/v1/runs/prepare", json=request)
        assert prepared_response.status_code == 201, prepared_response.text
        prepared = prepared_response.json()
        approval_id = prepared["approval"]["id"]
        client.post(f"/api/v1/runs/approvals/{approval_id}", json={"approved": True})
        response = client.post(
            "/api/v1/runs/execute",
            json={
                "adapter": "generic_process",
                "approval_id": approval_id,
                "plan": prepared["plan"],
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["decision"]["status"] == outcome, [
            e["metadata"].get("error") for e in result["evidence"]
        ]
        assert result["measurements"]["baseline"][0]["value"] == 100
        assert result["measurements"]["candidate"][0]["value"] == 10
        assert (project / "config.json").read_bytes() == original
        assert result["report"]["evidence_ids"]
        if outcome == "inconclusive":
            assert "insufficient samples" in result["decision"]["reason"]
    finally:
        get_settings.cache_clear()


def run_code(tmp_path: Path, code: str, limits: ResourceLimits | None = None) -> str:
    (tmp_path / "harness.py").write_text(code)
    return run_sandbox(
        tmp_path, ["/usr/bin/python3", "-I", "harness.py"], ".", [], {}, limits or ResourceLimits()
    )


def test_network_source_writes_and_host_reads_are_denied(tmp_path: Path) -> None:
    text = run_code(
        tmp_path,
        """import socket
from pathlib import Path
denied = []
try:
    socket.create_connection(("1.1.1.1", 80), timeout=.1)
except OSError:
    denied.append("network")
try:
    Path("undeclared.txt").write_text("escape")
except OSError:
    denied.append("write")
assert not Path("/home/navaneeth").exists()
print(",".join(denied))
""",
    )
    assert text.strip() == "network,write"
    assert not (tmp_path / "undeclared.txt").exists()


def test_timeout_output_bounds_and_nonzero_exit(tmp_path: Path) -> None:
    with pytest.raises(SandboxError, match="timeout"):
        run_code(tmp_path, "import time; time.sleep(20)", ResourceLimits(timeout_seconds=1))
    with pytest.raises(SandboxError, match="output limit"):
        run_code(tmp_path, "print('x'*100000)", ResourceLimits(output_bytes=1024))
    with pytest.raises(SandboxError, match="exited"):
        run_code(tmp_path, "raise RuntimeError('failed')")


def test_declared_output_is_writable_and_symlink_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "harness.py").write_text(
        'from pathlib import Path\nPath("out.json").write_text("{}")'
    )
    run_sandbox(
        tmp_path, ["/usr/bin/python3", "-I", "harness.py"], ".", ["out.json"], {}, ResourceLimits()
    )
    assert (tmp_path / "out.json").read_text() == "{}"
    (tmp_path / "link").symlink_to(tmp_path / "out.json")
    from ml_analyser.execution.sandbox import safe_path

    with pytest.raises(SandboxError, match="symlink"):
        safe_path(tmp_path, "link")


def test_limit_launcher_sets_resource_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    import resource

    from ml_analyser.execution.sandbox_limits import main

    calls = []
    monkeypatch.setattr(sys, "argv", ["launcher", "128", "3", "2048", "4", "/usr/bin/true"])
    monkeypatch.setattr(resource, "setrlimit", lambda key, value: calls.append((key, value)))
    monkeypatch.setattr("os.execv", lambda command, args: calls.append((command, args)))
    main()
    assert (resource.RLIMIT_CPU, (3, 3)) in calls
    assert (resource.RLIMIT_AS, (128 * 1024 * 1024, 128 * 1024 * 1024)) in calls
