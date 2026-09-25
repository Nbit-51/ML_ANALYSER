"""Repository preview evidence comes from bounded, non-executed files."""

import json
from pathlib import Path

from ml_analyser.agent.models import (
    ConstraintOperator,
    MetricConstraint,
    MetricDirection,
    Objective,
    SuccessContract,
)
from ml_analyser.tools.repository import RepositoryInventoryTool
from ml_analyser.tools.repository_context import RepositoryContextTool


def test_context_extracts_prior_metric_and_guardrail_without_running_code(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Example\nA CPU inference project. Median latency is measured on fixed inputs.\n",
        encoding="utf-8",
    )
    result_dir = tmp_path / "benchmark" / "results"
    result_dir.mkdir(parents=True)
    (result_dir / "sample.json").write_text(
        json.dumps(
            {
                "benchmark": "fixed-input test",
                "measurements": {"p50_latency_ms": 9.7, "max_abs_error": 0.000001},
            }
        ),
        encoding="utf-8",
    )
    kernel_dir = tmp_path / "engine" / "kernels"
    kernel_dir.mkdir(parents=True)
    (kernel_dir / "gemm.cpp").write_text("// representative kernel code\n", encoding="utf-8")
    (tmp_path / ".env").write_text("NEBIUS_API_KEY=private-test-value\n", encoding="utf-8")
    inventory = RepositoryInventoryTool().inspect(str(tmp_path))
    contract = SuccessContract(
        objective=Objective(metric="p50_latency_ms", direction=MetricDirection.MINIMIZE),
        constraints=[
            MetricConstraint(
                metric="max_abs_error", operator=ConstraintOperator.LTE, threshold=1e-5
            )
        ],
    )

    evidence = RepositoryContextTool().collect(tmp_path, inventory, contract)

    assert len(evidence) == 3
    metric_record = next(item for item in evidence if item.source.endswith("sample.json"))
    assert json.loads(metric_record.metadata["recorded_metrics_json"]) == {
        "p50_latency_ms": 9.7,
        "max_abs_error": 0.000001,
    }
    assert "prior record" in metric_record.claim
    assert "private-test-value" not in " ".join(item.claim for item in evidence)


def test_context_finds_relevant_regression_source_without_inference_assumptions(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "results"
    result_dir.mkdir()
    (result_dir / "house_prices.json").write_text(
        json.dumps({"validation_rmse": 0.72}), encoding="utf-8"
    )
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "train_house_prices.py").write_text(
        "def train_house_prices():\n    return 'regression'\n", encoding="utf-8"
    )
    (source_dir / "unrelated.py").write_text("# unrelated\n" * 100, encoding="utf-8")
    inventory = RepositoryInventoryTool().inspect(str(tmp_path))
    contract = SuccessContract(
        objective=Objective(metric="validation_rmse", direction=MetricDirection.MINIMIZE)
    )

    evidence = RepositoryContextTool().collect(tmp_path, inventory, contract)

    assert any(item.source == "src/train_house_prices.py" for item in evidence)


def test_context_ignores_invalid_results_and_unsafe_text(tmp_path: Path) -> None:
    result_dir = tmp_path / "results"
    result_dir.mkdir()
    (result_dir / "broken.json").write_text("{not-json", encoding="utf-8")
    (result_dir / "binary.json").write_bytes(b"\x00secret")
    (result_dir / "oversized.json").write_bytes(b"x" * (64 * 1024 + 1))
    inventory = RepositoryInventoryTool().inspect(str(tmp_path))
    contract = SuccessContract(
        objective=Objective(metric="validation_rmse", direction=MetricDirection.MINIMIZE)
    )

    evidence = RepositoryContextTool().collect(tmp_path, inventory, contract)

    assert evidence == []
    assert (
        RepositoryContextTool._find_metric(
            [{"ignored": True}, {"scores": [{"validation_rmse": 0.72}]}], "validation_rmse"
        )
        == 0.72
    )
    assert RepositoryContextTool._find_metric({"validation_rmse": True}, "validation_rmse") is None
