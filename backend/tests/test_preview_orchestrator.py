"""Tests for the read-only deterministic preview vertical slice."""

import asyncio
from pathlib import Path

from ml_analyser.agent.models import (
    ConstraintOperator,
    MetricConstraint,
    MetricDirection,
    Objective,
    RunState,
    SuccessContract,
)
from ml_analyser.agent.orchestrator import PreviewOrchestrator
from ml_analyser.agent.providers import DeterministicMockProvider
from ml_analyser.tools.repository import RepositoryInventoryTool


def test_preview_generates_falsifiable_ml_experiments_without_execution(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "executed.txt"
    (tmp_path / "train.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n",
        encoding="utf-8",
    )
    contract = SuccessContract(
        objective=Objective(
            metric="f1",
            direction=MetricDirection.MAXIMIZE,
            minimum_improvement=0.01,
        ),
        constraints=[
            MetricConstraint(
                metric="latency_ms",
                operator=ConstraintOperator.LT,
                threshold=100,
            )
        ],
    )
    orchestrator = PreviewOrchestrator(
        provider=DeterministicMockProvider(),
        inspector=RepositoryInventoryTool(),
    )

    result = asyncio.run(
        orchestrator.preview(
            project_id="sample-ml",
            project_root=tmp_path,
            success_contract=contract,
        )
    )

    assert result.final_state is RunState.COMPLETED
    assert RunState.EXECUTING not in result.state_history
    assert len(result.hypotheses) == 2
    assert len(result.experiments) == 2
    assert all(experiment.command is None for experiment in result.experiments)
    assert result.experiments[0].measurements == ["f1", "latency_ms"]
    assert not marker.exists()
