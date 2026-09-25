"""Behavioral coverage of generic contracts, evidence, protocols and failure states."""

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ml_analyser.adapters.process import ProcessAdapter, ProcessManifest, unique_json
from ml_analyser.adapters.registry import default_registry
from ml_analyser.agent.analytics import comparisons
from ml_analyser.agent.evaluator import DecisionEvaluator
from ml_analyser.agent.measurements import assess_reliability, summarize
from ml_analyser.agent.models import Measurement, ResourceUsage, SuccessContract
from ml_analyser.core.config import get_settings
from ml_analyser.execution.sandbox import SandboxError, safe_path
from ml_analyser.main import app
from ml_analyser.tools.capabilities import detect_capabilities
from ml_analyser.tools.repository import RepositoryInventoryTool

ROOT = Path(__file__).resolve().parents[2]
CLIENT = TestClient(app)


@pytest.fixture
def configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in ("cli-benchmark-demo", "build-test-demo", "ml-regression-demo", "ml-training-demo"):
        shutil.copytree(ROOT / "workspaces" / name, tmp_path / name)
    monkeypatch.setenv("ML_ANALYSER_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("ML_ANALYSER_EXECUTION_ROOT", str(tmp_path / "executions"))
    monkeypatch.setenv("ML_ANALYSER_STATE_DATABASE", str(tmp_path / "state.db"))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def prepare(root: Path, project: str = "cli-benchmark-demo") -> dict:
    payload = json.loads((root / project / "prepare_request.json").read_text())
    response = CLIENT.post("/api/v1/runs/prepare", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def approve(prepared: dict) -> dict:
    approval_id = prepared["approval"]["id"]
    assert (
        CLIENT.post(f"/api/v1/runs/approvals/{approval_id}", json={"approved": True}).status_code
        == 200
    )
    return {"adapter": prepared["adapter"], "approval_id": approval_id, "plan": prepared["plan"]}


def fake_harness(monkeypatch: pytest.MonkeyPatch, *, mode: str = "normal") -> list[str]:
    """Deterministic runner double; real containment is tested separately on Linux."""
    order = []
    monkeypatch.setattr("ml_analyser.agent.process_benchmark.sandbox_available", lambda: True)

    def run(root, command, cwd, outputs, env, limits):
        config = json.loads((root / "config.json").read_text())
        order.append(root.name)
        if mode == "failure":
            raise SandboxError("intentional failed measurement")
        value = config["repeats"]
        if mode == "variance" and len(order) % 3 == 0:
            value *= 10
        text = json.dumps(
            {
                "metrics": [
                    {"name": "work_units", "value": value, "unit": "operations"},
                    {
                        "name": "checks_passed",
                        "value": 0 if config["incorrect"] else 1,
                        "unit": "ratio",
                    },
                    {"name": "elapsed_ms", "value": 1, "unit": "ms"},
                ],
                "correctness": "bad" if config["incorrect"] else "same",
            }
        )
        for relative in outputs:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        return text

    monkeypatch.setattr("ml_analyser.adapters.process.run_sandbox", run)
    return order


@pytest.mark.parametrize("project", ["ml-training-demo", "ml-regression-demo"])
def test_real_ml_metrics_cross_generic_api_and_persist_report(
    configured: Path, project: str
) -> None:
    if project == "ml-training-demo":
        path = configured / project / "prepare_request.json"
        payload = json.loads(path.read_text())
        payload["adapter"] = "ml_training"
        path.write_text(json.dumps(payload))
    prepared = prepare(configured, project)
    execution = CLIENT.post("/api/v1/runs/execute", json=approve(prepared))
    assert execution.status_code == 200, execution.text
    result = execution.json()
    assert result["decision"]["status"] == "accepted"
    assert result["comparisons"]
    if project == "ml-regression-demo":
        metric = result["comparisons"][0]
        assert metric["name"] == "validation_rmse"
        assert metric["baseline"] == 2 and metric["candidate"] == 0
        assert metric["unit"] == "target_units" and metric["direction"] == "minimize"
    report = CLIENT.get(f"/api/v1/runs/{result['run_id']}/report").json()
    assert report == result
    assert report["report"]["source_fingerprint"]
    assert len(result["experiments"]) == 2
    assert result["experiments"][1]["parent_experiment_id"] == result["experiments"][0]["id"]


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("normal", "accepted"),
        ("variance", "inconclusive"),
        ("failure", "inconclusive"),
        ("incorrect", "rejected"),
    ],
)
def test_protocol_decisions_evidence_and_source_isolation(
    configured: Path, monkeypatch: pytest.MonkeyPatch, mode: str, expected: str
) -> None:
    project = configured / "cli-benchmark-demo"
    if mode == "incorrect":
        path = project / "repo_benchmark.json"
        payload = json.loads(path.read_text())
        payload["candidate_overrides"]["incorrect"] = True
        path.write_text(json.dumps(payload))
    original = (project / "config.json").read_bytes()
    order = fake_harness(monkeypatch, mode=mode)
    prepared = prepare(configured)
    request = approve(prepared)
    response = CLIENT.post("/api/v1/runs/execute", json=request)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["decision"]["status"] == expected
    assert result["disposition"] == ("retained" if expected == "accepted" else "discarded")
    assert (project / "config.json").read_bytes() == original
    assert order[:4] == ["baseline", "candidate", "candidate", "baseline"]
    assert sum(e["kind"] == "tool_output" for e in result["evidence"]) == 12
    known_ids = {e["id"] for e in result["evidence"]}
    assert all(
        set(c["evidence_ids"]) <= known_ids for c in result["repository_summary"]["capabilities"]
    )
    if mode != "failure":
        measurement = result["measurements"]["candidate"][0]
        assert len(measurement["raw_samples"]) == 5
        assert measurement["summary"]["count"] == 5
        assert measurement["environment_fingerprint"]
    else:
        assert "Missing required" in result["decision"]["reason"]
        assert any(e["metadata"].get("error") for e in result["evidence"])
    assert CLIENT.post("/api/v1/runs/execute", json=request).status_code == 409


def test_generic_start_persists_normalized_snapshot(
    configured: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_harness(monkeypatch)
    prepared = prepare(configured)
    request = approve(prepared)
    started = CLIENT.post("/api/v1/runs/start", json=request)
    assert started.status_code == 202
    live = CLIENT.get(f"/api/v1/runs/live/{prepared['plan']['run_id']}").json()
    assert live["status"] == "completed"
    assert live["result"]["comparisons"][0]["name"]
    assert "executing" in live["events"]


def test_approval_change_and_no_sandbox_are_fail_closed(
    configured: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_harness(monkeypatch)
    prepared = prepare(configured)
    request = approve(prepared)
    request["plan"]["manifest"]["repetitions"] += 1
    assert CLIENT.post("/api/v1/runs/execute", json=request).status_code == 409
    request["plan"]["manifest"]["repetitions"] -= 1
    (configured / "cli-benchmark-demo" / "config.json").write_text(
        '{"repeats":42,"incorrect":false}'
    )
    response = CLIENT.post("/api/v1/runs/execute", json=request)
    assert "changed after preparation" in response.text
    monkeypatch.setattr("ml_analyser.agent.process_benchmark.sandbox_available", lambda: False)
    assert "preview only" in CLIENT.post("/api/v1/runs/execute", json=request).text
    assert CLIENT.get("/api/v1/runs/missing/report").status_code == 404
    assert (
        CLIENT.post(
            "/api/v1/runs/prepare",
            json={
                "adapter": "unknown",
                "project_path": "cli-benchmark-demo",
                "success_contract": prepared["plan"]["success_contract"],
            },
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "mutation,match",
    [
        ({"command": ["sh", "-c", "echo unsafe"]}, "executable"),
        ({"environment": {"NEBIUS_API_KEY": "secret"}}, "allowlist"),
        ({"metrics_file": "out.json"}, "allowed output"),
        ({"candidate_overrides": {}}, "declared change"),
        ({"allowed_output_paths": ["x", "x"]}, "duplicate"),
        ({"command": ["/usr/bin/python3", "\x00"]}, "argument"),
        ({"network": "allowed"}, "denied"),
    ],
)
def test_manifest_rejects_unsafe_declarations(mutation: dict, match: str) -> None:
    payload = json.loads((ROOT / "workspaces/cli-benchmark-demo/repo_benchmark.json").read_text())
    payload.update(mutation)
    with pytest.raises(ValidationError, match=match):
        ProcessManifest.model_validate(payload)


@pytest.mark.parametrize(
    "text,match",
    [
        ("{bad", "malformed"),
        ('{"metrics":[],"correctness":"same"}', "missing"),
        ('{"metrics":[],"metrics":[],"correctness":"same"}', "duplicate"),
    ],
)
def test_metric_output_is_strict(
    configured: Path, monkeypatch: pytest.MonkeyPatch, text: str, match: str
) -> None:
    adapter = ProcessAdapter()
    project = configured / "cli-benchmark-demo"
    manifest = adapter.load_manifest(project)
    monkeypatch.setattr("ml_analyser.adapters.process.run_sandbox", lambda *args: text)
    with pytest.raises(SandboxError, match=match):
        adapter.measure(project, manifest)


def test_detection_is_evidence_linked_and_byte_based(tmp_path: Path) -> None:
    for file in (
        "CMakeLists.txt",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "Dockerfile",
        "main.py",
        "pytest.ini",
        "api.py",
        "train.py",
        "model.onnx",
        "data.csv",
        ".github/workflows/ci.yml",
    ):
        path = tmp_path / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# not executed\n")
    summary, evidence = detect_capabilities(RepositoryInventoryTool().inspect(str(tmp_path)))
    assert summary.language_bytes["python"] == sum(
        (tmp_path / name).stat().st_size for name in ("main.py", "api.py", "train.py")
    )
    assert {c.name for c in summary.capabilities} >= {
        "CMake",
        "Node",
        "Cargo",
        "Go modules",
        "Docker",
    }
    assert all(set(c.evidence_ids) <= {e.id for e in evidence} for c in summary.capabilities)
    assert not any(c.provenance == "measured" for c in summary.capabilities)
    registry = default_registry()
    with pytest.raises(ValueError, match="already registered"):
        registry.register(registry.get("ml_training"))
    with pytest.raises(ValueError, match="unsupported"):
        registry.get("invented")


def test_samples_units_finiteness_and_reliability() -> None:
    for value in (float("nan"), float("inf"), True):
        with pytest.raises(ValidationError):
            Measurement(metric="m", value=value, evidence_ids=["e"])
    with pytest.raises(ValueError, match="empty"):
        summarize([])
    a = Measurement(
        metric="m",
        value=2,
        raw_samples=[2, 2, 2],
        unit="s",
        evidence_ids=["a"],
        environment_fingerprint="host",
    )
    b = a.model_copy(update={"environment_fingerprint": "other", "unit": "ms", "raw_samples": [1]})
    reasons = assess_reliability([a], [b], {"m"}).reasons
    assert any("environment" in reason for reason in reasons)
    assert any("units" in reason for reason in reasons)
    assert any("insufficient" in reason for reason in reasons)
    b = a.model_copy(update={"raw_samples": [-1, 0, 1], "failed_sample_count": 1})
    assert len(assess_reliability([a], [b], {"m"}).reasons) == 2
    contract = SuccessContract.model_validate(
        {"objective": {"metric": "m", "direction": "minimize"}}
    )
    decision = DecisionEvaluator().evaluate(
        experiment_id="x", contract=contract, baseline=[a], candidate=[a], usage=ResourceUsage()
    )
    rows = comparisons({"baseline": [a], "candidate": [a]}, contract, decision)
    assert rows[0].delta == 0 and rows[0].percentage_delta == 0
    with pytest.raises(ValueError, match="duplicate"):
        DecisionEvaluator().evaluate(
            experiment_id="x",
            contract=contract,
            baseline=[a, a],
            candidate=[a],
            usage=ResourceUsage(),
        )


def test_paths_and_duplicate_json(tmp_path: Path) -> None:
    for path in ("../escape", "/absolute", "C:/escape", "a\\b", ""):
        with pytest.raises(SandboxError):
            safe_path(tmp_path, path, exists=False)
    with pytest.raises(ValueError, match="duplicate"):
        unique_json([("a", 1), ("a", 2)])
    assert safe_path(tmp_path, "out.json", exists=False) == tmp_path / "out.json"


def test_incomplete_inventory_cannot_be_executed(tmp_path: Path) -> None:
    from ml_analyser.agent.process_benchmark import source_fingerprint

    (tmp_path / "large.py").write_text("1234")
    with pytest.raises(SandboxError, match="complete inventory"):
        source_fingerprint(RepositoryInventoryTool(max_hash_bytes=1).inspect(str(tmp_path)))


@pytest.mark.parametrize("incorrect", [False, True])
def test_artifacts_survive_workspace_disposition(
    configured: Path, monkeypatch: pytest.MonkeyPatch, incorrect: bool
) -> None:
    import base64

    fake_harness(monkeypatch)
    path = configured / "cli-benchmark-demo" / "repo_benchmark.json"
    data = json.loads(path.read_text())
    data.update(metrics_file="measured.json", allowed_output_paths=["measured.json"])
    data["candidate_overrides"]["incorrect"] = incorrect
    path.write_text(json.dumps(data))
    prepared = prepare(configured)
    response = CLIENT.post("/api/v1/runs/execute", json=approve(prepared))
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["artifacts"]) == 2
    for artifact in result["artifacts"]:
        payload = json.loads(base64.b64decode(artifact["content_base64"]))
        assert payload["correctness"] in {"same", "bad"}
        assert len(artifact["evidence_ids"]) == 6
        assert artifact["size_bytes"] > 0
    assert result["measurements"]["candidate"][0]["artifact_ids"]
    assert not (configured / "cli-benchmark-demo" / "measured.json").exists()
    assert (
        CLIENT.get(f"/api/v1/runs/{result['run_id']}/report").json()["artifacts"]
        == result["artifacts"]
    )


@pytest.mark.parametrize(
    "metrics,match",
    [
        ([{"name": "m", "value": 0.5, "unit": "wrong"}], "wrong metric unit"),
        ([{"name": "m", "value": 0.5, "unit": "u"}] * 2, "duplicate metric"),
        ([{"name": "m", "value": float("nan"), "unit": "u"}], "malformed"),
        ([{"name": "m", "value": float("inf"), "unit": "u"}], "malformed"),
        ([{"name": "m", "value": True, "unit": "u"}], "malformed"),
        ([{"name": "m", "value": 2, "unit": "u"}], "bounds"),
        ([{"name": "process_duration_ms", "value": 1, "unit": "ms"}], "reserved"),
    ],
)
def test_metric_semantics_reject_invalid_observations(
    configured: Path, monkeypatch: pytest.MonkeyPatch, metrics: list, match: str
) -> None:
    from ml_analyser.agent.models import MetricDefinition

    adapter = ProcessAdapter()
    root = configured / "cli-benchmark-demo"
    manifest = adapter.load_manifest(root)
    manifest.metric_definitions = [MetricDefinition(name="m", unit="u", minimum=0, maximum=1)]
    monkeypatch.setattr(
        "ml_analyser.adapters.process.run_sandbox",
        lambda *args: json.dumps({"metrics": metrics, "correctness": "same"}),
    )
    with pytest.raises(SandboxError, match=match):
        adapter.measure(root, manifest)


@pytest.mark.parametrize(
    "mutation,match",
    [
        ({"config_file": "."}, "must be a file"),
        ({"working_directory": "config.json"}, "must be a directory"),
        ({"allowed_output_paths": ["config.json"]}, "overwrite"),
        ({"allowed_output_paths": ["../escape"]}, "traversal"),
        ({"config_file": "../escape"}, "traversal"),
    ],
)
def test_profile_paths_are_validated_before_approval(
    configured: Path, mutation: dict, match: str
) -> None:
    root = configured / "cli-benchmark-demo"
    path = root / "repo_benchmark.json"
    data = json.loads(path.read_text())
    data.update(mutation)
    path.write_text(json.dumps(data))
    with pytest.raises(SandboxError, match=match):
        ProcessAdapter().load_manifest(root)
    readiness = default_registry().describe(root)
    assert (
        next(a for a in readiness if a.adapter == "generic_process").status
        == "detected_but_needs_configuration"
    )


def test_build_dependency_indicators_are_inferred(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies=["pytest", "torch", "fastapi"]'
    )
    summary, evidence = detect_capabilities(RepositoryInventoryTool().inspect(str(tmp_path)))
    inferred = [c for c in summary.capabilities if c.provenance == "inferred"]
    assert len(inferred) == 3
    assert all(c.confidence < 1 for c in inferred)
    assert len({c.id for c in summary.capabilities}) == len(summary.capabilities)
    assert evidence


def test_background_failure_is_persisted_without_measurement_claim(
    configured: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ml_analyser.agent.process_benchmark.sandbox_available", lambda: False)
    prepared = prepare(configured)
    request = approve(prepared)
    assert CLIENT.post("/api/v1/runs/start", json=request).status_code == 202
    live = CLIENT.get(f"/api/v1/runs/live/{prepared['plan']['run_id']}").json()
    assert live["status"] == "failed" and live["result"] is None
    assert "preview only" in live["error"]


def test_new_api_errors_do_not_create_runs(configured: Path) -> None:
    request = {
        "adapter": "generic_process",
        "project_path": "../escape",
        "success_contract": {"objective": {"metric": "m", "direction": "minimize"}},
    }
    assert CLIENT.post("/api/v1/runs/prepare", json=request).status_code == 422
    request["project_path"] = "cli-benchmark-demo"
    assert "declared" in CLIENT.post("/api/v1/runs/prepare", json=request).text
    request["success_contract"]["objective"]["metric"] = "work_units"
    request["success_contract"]["budget"] = {"max_cpu_seconds": 10}
    assert "accounting" in CLIENT.post("/api/v1/runs/prepare", json=request).text
