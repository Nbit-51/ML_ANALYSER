"""Integration tests for the approval-gated backend benchmark adapter."""

import asyncio
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ml_analyser.adapters.backend_http import BackendHttpBenchmarkAdapter
from ml_analyser.agent.approval import ApprovalService
from ml_analyser.agent.backend_benchmark import BackendBenchmarkPipeline
from ml_analyser.agent.evaluator import DecisionEvaluator
from ml_analyser.agent.models import (
    ApprovalStatus,
    ComputeBudget,
    ConstraintOperator,
    DecisionStatus,
    MetricConstraint,
    MetricDirection,
    Objective,
    SuccessContract,
)
from ml_analyser.agent.providers import DeterministicMockProvider
from ml_analyser.core.config import get_settings
from ml_analyser.execution import IsolatedWorkspaceManager
from ml_analyser.main import app
from ml_analyser.persistence import SQLiteRunStore
from ml_analyser.persistence.sqlite import InvalidApprovalTransitionError
from ml_analyser.tools.repository import RepositoryInventoryTool

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEMO_SOURCE = REPOSITORY_ROOT / "workspaces" / "backend-benchmark-demo"
client = TestClient(app)


def _contract() -> SuccessContract:
    return SuccessContract(
        objective=Objective(
            metric="p95_latency_ms",
            direction=MetricDirection.MINIMIZE,
            target=40.0,
            minimum_improvement=10.0,
        ),
        constraints=[
            MetricConstraint(
                metric="error_rate",
                operator=ConstraintOperator.LTE,
                threshold=0.0,
            ),
            MetricConstraint(
                metric="response_hash_matches",
                operator=ConstraintOperator.EQ,
                threshold=1.0,
            ),
        ],
        budget=ComputeBudget(max_wall_clock_seconds=10, max_experiments=1),
    )


def _copy_demo(tmp_path: Path) -> Path:
    project = tmp_path / "backend-demo"
    shutil.copytree(DEMO_SOURCE, project)
    return project


def test_adapter_measures_real_localhost_improvement(tmp_path: Path) -> None:
    project = _copy_demo(tmp_path)
    manager = IsolatedWorkspaceManager(tmp_path / "executions")
    adapter = BackendHttpBenchmarkAdapter()
    baseline_handle = manager.create(run_id="adapter-run", label="baseline", source_root=project)
    candidate_handle = manager.create(run_id="adapter-run", label="candidate", source_root=project)
    baseline_manifest = adapter.load_manifest(baseline_handle.workspace_root)
    candidate_manifest = adapter.load_manifest(candidate_handle.workspace_root)
    adapter.apply_candidate(candidate_handle.workspace_root, candidate_manifest)

    baseline = adapter.measure(baseline_handle.workspace_root, baseline_manifest)
    candidate = adapter.measure(candidate_handle.workspace_root, candidate_manifest)

    assert baseline.p95_latency_ms - candidate.p95_latency_ms > 10
    assert candidate.p95_latency_ms < 40
    assert baseline.response_hash == candidate.response_hash
    assert baseline.error_rate == candidate.error_rate == 0


def test_pipeline_requires_approval_retains_candidate_and_blocks_replay(
    tmp_path: Path,
) -> None:
    project = _copy_demo(tmp_path)
    store = SQLiteRunStore(tmp_path / "runs.db")
    approvals = ApprovalService(store)
    pipeline = BackendBenchmarkPipeline(
        provider=DeterministicMockProvider(),
        inspector=RepositoryInventoryTool(),
        approvals=approvals,
        evaluator=DecisionEvaluator(),
        workspaces=IsolatedWorkspaceManager(tmp_path / "executions"),
        store=store,
    )
    prepared = asyncio.run(
        pipeline.prepare(
            project_id="backend-demo",
            project_path="backend-demo",
            project_root=project,
            success_contract=_contract(),
        )
    )

    with pytest.raises(InvalidApprovalTransitionError, match="pending"):
        pipeline.execute(
            plan=prepared.plan,
            approval_id=prepared.approval.id,
            project_root=project,
        )

    approvals.decide(prepared.approval.id, approved=True, reason="Fixture reviewed")
    result = pipeline.execute(
        plan=prepared.plan,
        approval_id=prepared.approval.id,
        project_root=project,
    )

    assert result.approval.status is ApprovalStatus.CONSUMED
    assert result.decision.status is DecisionStatus.ACCEPTED
    assert result.disposition == "retained"
    assert result.original_project_modified is False
    assert result.retained_candidate_workspace is not None
    retained_config = Path(result.retained_candidate_workspace) / "config.json"
    original_config = project / "config.json"
    assert json.loads(retained_config.read_text(encoding="utf-8"))["delay_seconds"] == 0.001
    assert json.loads(original_config.read_text(encoding="utf-8"))["delay_seconds"] == 0.025
    assert len(store.list_for_run(result.run_id)) == 3
    assert len(store.list_experiments(result.run_id)) == 2

    with pytest.raises(InvalidApprovalTransitionError, match="consumed"):
        pipeline.execute(
            plan=prepared.plan,
            approval_id=prepared.approval.id,
            project_root=project,
        )


def test_rejected_candidate_is_discarded_without_modifying_source(tmp_path: Path) -> None:
    project = _copy_demo(tmp_path)
    manifest_path = project / "backend_benchmark.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["candidate_overrides"] = {"delay_seconds": 0.05}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    store = SQLiteRunStore(tmp_path / "runs.db")
    approvals = ApprovalService(store)
    execution_root = tmp_path / "executions"
    pipeline = BackendBenchmarkPipeline(
        provider=DeterministicMockProvider(),
        inspector=RepositoryInventoryTool(),
        approvals=approvals,
        evaluator=DecisionEvaluator(),
        workspaces=IsolatedWorkspaceManager(execution_root),
        store=store,
    )
    prepared = asyncio.run(
        pipeline.prepare(
            project_id="backend-demo",
            project_path="backend-demo",
            project_root=project,
            success_contract=_contract(),
        )
    )
    approvals.decide(prepared.approval.id, approved=True)

    result = pipeline.execute(
        plan=prepared.plan,
        approval_id=prepared.approval.id,
        project_root=project,
    )

    assert result.decision.status is DecisionStatus.REJECTED
    assert result.disposition == "discarded"
    assert result.retained_candidate_workspace is None
    assert not (execution_root / result.run_id).exists()
    assert (
        json.loads((project / "config.json").read_text(encoding="utf-8"))["delay_seconds"] == 0.025
    )


def test_backend_api_prepare_approve_execute_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_demo(tmp_path)
    monkeypatch.setenv("ML_ANALYSER_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("ML_ANALYSER_STATE_DATABASE", str(tmp_path / "api.db"))
    monkeypatch.setenv("ML_ANALYSER_EXECUTION_ROOT", str(tmp_path / "api-executions"))
    get_settings.cache_clear()
    prepare_payload = {
        "project_path": "backend-demo",
        "project_id": "backend-demo",
        "success_contract": _contract().model_dump(mode="json"),
    }
    try:
        prepared_response = client.post(
            "/api/v1/runs/backend-benchmark/prepare", json=prepare_payload
        )
        assert prepared_response.status_code == 201
        prepared = prepared_response.json()
        approval_id = prepared["approval"]["id"]

        approval_response = client.post(
            f"/api/v1/runs/approvals/{approval_id}",
            json={"approved": True, "reason": "Fixture reviewed"},
        )
        assert approval_response.status_code == 200

        execution_response = client.post(
            "/api/v1/runs/backend-benchmark/execute",
            json={"approval_id": approval_id, "plan": prepared["plan"]},
        )
    finally:
        get_settings.cache_clear()

    assert execution_response.status_code == 200
    body = execution_response.json()
    assert body["decision"]["status"] == "accepted"
    assert body["disposition"] == "retained"
    assert body["candidate"]["p95_latency_ms"] < body["baseline"]["p95_latency_ms"]
