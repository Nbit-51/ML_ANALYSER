"""End-to-end tests for the hidden classification-threshold failure demo."""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ml_analyser.adapters.ml_threshold import (
    AdapterValidationError,
    ClassificationThresholdAdapter,
)
from ml_analyser.agent.evaluator import DecisionEvaluator
from ml_analyser.agent.ml_demo import ThresholdDemoService
from ml_analyser.agent.models import (
    ComputeBudget,
    ConstraintOperator,
    DecisionStatus,
    MetricConstraint,
    MetricDirection,
    Objective,
    RunState,
    SuccessContract,
)
from ml_analyser.agent.providers import DeterministicMockProvider
from ml_analyser.core.config import get_settings
from ml_analyser.main import app
from ml_analyser.persistence import SQLiteRunStore
from ml_analyser.tools.repository import RepositoryInventoryTool

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEMO_PROJECT = REPOSITORY_ROOT / "workspaces" / "hidden-threshold-demo"
client = TestClient(app)


def _contract() -> SuccessContract:
    return SuccessContract(
        objective=Objective(
            metric="f1",
            direction=MetricDirection.MAXIMIZE,
            minimum_improvement=0.01,
        ),
        constraints=[
            MetricConstraint(
                metric="recall",
                operator=ConstraintOperator.GTE,
                threshold=0.8,
            )
        ],
        budget=ComputeBudget(max_wall_clock_seconds=30, max_experiments=2),
    )


def test_adapter_discovers_hidden_threshold_failure() -> None:
    adapter = ClassificationThresholdAdapter()
    manifest, rows = adapter.load(DEMO_PROJECT)

    baseline = adapter.measure(rows, manifest.baseline_threshold)
    candidate = adapter.find_best_threshold(rows, objective_metric="f1")

    assert baseline.threshold == 0.5
    assert baseline.metrics["f1"] == pytest.approx(0.7692307692)
    assert candidate.threshold == pytest.approx(0.595)
    assert candidate.metrics["f1"] == pytest.approx(0.9090909091)
    assert candidate.metrics["recall"] == pytest.approx(1.0)


def test_adapter_rejects_prediction_path_traversal(tmp_path: Path) -> None:
    outside = tmp_path / "outside.csv"
    outside.write_text("label,score\n1,0.9\n0,0.1\n", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    (project / "ml_analyser.json").write_text(
        '{"adapter":"ml_classification_threshold","predictions_file":"../outside.csv"}',
        encoding="utf-8",
    )

    with pytest.raises(AdapterValidationError, match="must stay inside"):
        ClassificationThresholdAdapter().load(project)


def test_demo_runs_full_measurement_decision_and_persistence_loop(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "demo.db")
    service = ThresholdDemoService(
        provider=DeterministicMockProvider(),
        inspector=RepositoryInventoryTool(),
        evaluator=DecisionEvaluator(),
        store=store,
    )

    result = asyncio.run(
        service.run(
            project_id="hidden-threshold-demo",
            project_root=DEMO_PROJECT,
            success_contract=_contract(),
        )
    )

    assert result.final_state is RunState.COMPLETED
    assert RunState.EXECUTING in result.state_history
    assert result.decision.status is DecisionStatus.ACCEPTED
    assert result.candidate.metrics["f1"] > result.baseline.metrics["f1"]
    assert result.persisted
    assert len(store.list_for_run(result.run_id)) == 3
    assert len(store.list_experiments(result.run_id)) == 2


def test_demo_api_requires_explicit_approval_and_returns_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ML_ANALYSER_WORKSPACE_ROOT", str(REPOSITORY_ROOT / "workspaces"))
    monkeypatch.setenv("ML_ANALYSER_STATE_DATABASE", str(tmp_path / "api-demo.db"))
    get_settings.cache_clear()
    payload = {
        "project_path": "hidden-threshold-demo",
        "success_contract": _contract().model_dump(mode="json"),
    }
    try:
        unapproved = client.post("/api/v1/runs/ml-threshold-demo", json=payload)
        approved = client.post(
            "/api/v1/runs/ml-threshold-demo",
            json={**payload, "approved": True},
        )
    finally:
        get_settings.cache_clear()

    assert unapproved.status_code == 409
    assert approved.status_code == 200
    body = approved.json()
    assert body["decision"]["status"] == "accepted"
    assert body["candidate"]["metrics"]["f1"] > body["baseline"]["metrics"]["f1"]
    assert body["persisted"] is True
