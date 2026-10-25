"""Independent metric calculations, masked regressions and bounded public CSV evaluation."""

import csv
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ml_analyser.api.routes.evaluation import comparison_slot
from ml_analyser.evaluation.predictions import PredictionRequest, compare_predictions
from ml_analyser.main import app

EXAMPLES = Path(__file__).resolve().parents[2] / "frontend/examples"


def request(name: str, *, task: str = "classification", **overrides: object) -> PredictionRequest:
    return PredictionRequest.model_validate(
        {
            "task": task,
            "primary_metric": "f1_macro" if task == "classification" else "rmse",
            "csv_text": (EXAMPLES / f"predictions-{name}.csv").read_text(encoding="utf-8"),
            **overrides,
        }
    )


def test_improved_overall_f1_does_not_hide_a_cohort_regression() -> None:
    result = compare_predictions(request("hidden-regression"))
    assert result.baseline["accuracy"] == pytest.approx(0.78)
    assert result.candidate["accuracy"] == pytest.approx(0.90)
    assert result.improvement > 0 and result.improvement_interval[0] > 0
    mobile = next(item for item in result.slices if item.name == "mobile")
    assert mobile.baseline == pytest.approx(0.9) and mobile.candidate == pytest.approx(0.6)
    assert mobile.passed is False and mobile.regression == pytest.approx(0.3)
    assert result.decision == "rejected"


def test_confusion_counts_and_macro_metrics_match_hand_calculation() -> None:
    text = "actual,baseline,candidate\n" + "a,a,a\na,b,a\nb,b,b\nb,c,b\nc,c,c\nc,a,c\n" * 20
    item = request("classification-improvement", csv_text=text)
    result = compare_predictions(item)
    assert result.confusion_matrices["baseline"] == [[20, 20, 0], [0, 20, 20], [20, 0, 20]]
    assert result.labels == ["a", "b", "c"]
    assert all(value == pytest.approx(0.5) for value in result.baseline.values())
    assert all(value == pytest.approx(1.0) for value in result.candidate.values())
    assert result.decision == "accepted"


def test_regression_metrics_and_constant_target_r2() -> None:
    item = request("regression-improvement", task="regression")
    result = compare_predictions(item)
    assert result.baseline["mae"] == result.baseline["rmse"] == 8
    assert result.candidate["mae"] == result.candidate["rmse"] == 2
    assert result.improvement_interval == (6, 6)
    assert result.direction == "minimize" and result.decision == "accepted"
    item.csv_text = "actual,baseline,candidate\n" + "1,3,2\n" * 20
    constant = compare_predictions(item)
    assert constant.baseline["r2"] is None and constant.candidate["r2"] is None
    item.csv_text = "actual,baseline,candidate\n0,2,1\n1,3,2\n2,4,3\n3,5,4\n"
    hand = compare_predictions(item)
    assert hand.baseline["r2"] == pytest.approx(-2.2)
    assert hand.candidate["r2"] == pytest.approx(0.2)
    assert hand.decision == "inconclusive"


def test_improvement_with_uncertainty_or_small_cohorts_is_inconclusive() -> None:
    data = "actual,baseline,candidate\n" + "a,a,a\nb,b,b\n" * 9 + "a,b,a\nb,b,b\n"
    result = compare_predictions(request("classification-improvement", csv_text=data))
    assert result.improvement > 0.01 and result.improvement_interval[0] == 0
    assert result.decision == "inconclusive"
    small = request("classification-improvement", minimum_slice_size=101)
    assert compare_predictions(small).decision == "inconclusive"
    worse = request("classification-improvement", minimum_improvement=0.9)
    assert compare_predictions(worse).decision == "rejected"


def test_class_recall_catches_a_minority_failure_without_explicit_cohorts() -> None:
    data = "actual,baseline,candidate\n" + "a,b,a\n" * 70 + "a,a,a\n" * 20 + "b,b,a\n" * 10
    result = compare_predictions(
        request("classification-improvement", csv_text=data, primary_metric="accuracy")
    )
    assert result.candidate["accuracy"] > result.baseline["accuracy"]
    assert any(
        item.kind == "class" and item.name == "b" and item.passed is False for item in result.slices
    )
    assert result.decision == "rejected"


def test_csv_quoting_unicode_bom_and_line_endings_replay_identically() -> None:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["id", "actual", "baseline", "candidate", "cohort"])
    for number in range(30):
        writer.writerow(
            [
                f"private-sample-{number}",
                'label, "one"',
                'label, "one"',
                'label, "one"',
                "français, mobile",
            ]
        )
    one = request("classification-improvement", csv_text=output.getvalue(), minimum_improvement=0)
    before = compare_predictions(one)
    one.csv_text = "\ufeff" + one.csv_text.replace("\n", "\r\n")
    after = compare_predictions(one)
    assert before == after
    assert after.labels == ['label, "one"'] and after.decision == "accepted"
    assert "private-sample-" not in after.model_dump_json()


@pytest.mark.parametrize(
    "text",
    [
        "",
        "actual,actual,baseline,candidate\na,a,a,a",
        "actual,baseline\na,a",
        "actual,baseline,candidate\na,a,a,extra",
        'actual,baseline,candidate\n"unterminated',
        "id,actual,baseline,candidate\n1,a,a,a\n1,b,b,b",
        "actual,baseline,candidate\na,,a",
        "actual,baseline,candidate,secret\na,a,a,x",
        "actual,baseline,candidate\na,a,a",
    ],
)
def test_invalid_csv_is_rejected_without_evaluation(text: str) -> None:
    with pytest.raises((ValueError, ValidationError)):
        compare_predictions(request("classification-improvement", csv_text=text))


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1000000000001", "not-numeric"])
def test_nonfinite_or_unbounded_regression_data_is_rejected(number: str) -> None:
    with pytest.raises(ValueError):
        compare_predictions(
            request(
                "regression-improvement",
                task="regression",
                csv_text=f"actual,baseline,candidate\n1,{number},2\n2,2,2\n",
            )
        )


@pytest.mark.parametrize("limit", ["rows", "labels", "cohorts", "bytes", "cell"])
def test_input_resource_limits(limit: str) -> None:
    if limit == "rows":
        data = "actual,baseline,candidate\n" + "a,a,a\n" * 5001
    elif limit == "labels":
        data = "actual,baseline,candidate\n" + "".join(f"{n},{n},{n}\n" for n in range(21))
    elif limit == "cohorts":
        data = "actual,baseline,candidate,cohort\n" + "".join(f"a,a,a,{n}\n" for n in range(21))
    elif limit == "cell":
        data = "actual,baseline,candidate\n" + "x" * 161 + ",a,a\na,a,a\n"
    else:
        data = "actual,baseline,candidate\n" + "é" * 1_000_001
    with pytest.raises(ValueError):
        compare_predictions(request("classification-improvement", csv_text=data))


def test_public_endpoint_is_bounded_and_does_not_call_a_model_or_create_data_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ML_ANALYSER_DEPLOYMENT_MODE", "judge")
    client = TestClient(app)
    payload = request("classification-improvement").model_dump()
    response = client.post("/api/v1/evaluation/compare", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "accepted"
    assert not list(tmp_path.iterdir())
    assert response.headers["cache-control"] == "no-store"
    assert (
        client.post(
            "/api/v1/evaluation/compare", json={**payload, "minimum_improvement": True}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/evaluation/compare", json={**payload, "primary_metric": "rmse"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/evaluation/compare", json={**payload, "maximum_slice_regression": 2}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/evaluation/compare", json=payload, headers={"Origin": "https://bad.invalid"}
        ).status_code
        == 403
    )
    comparison_slot.acquire()
    try:
        assert client.post("/api/v1/evaluation/compare", json=payload).status_code == 429
    finally:
        comparison_slot.release()
    assert client.post("/api/v1/evaluation/compare", json=payload).status_code == 200
    assert client.get("/evaluate").status_code == 200


def test_report_is_deterministic_and_any_data_or_rule_change_breaks_replay() -> None:
    item = request("classification-improvement")
    first = compare_predictions(item)
    assert compare_predictions(item) == first
    assert len(first.report_sha256) == 64
    serialized = json.loads(first.model_dump_json())
    assert "csv_text" not in serialized and serialized["bootstrap_rounds"] == 200
    item.maximum_slice_regression = 0.05
    assert compare_predictions(item).report_sha256 != first.report_sha256
    item.csv_text = item.csv_text.replace("desktop-0", "changed-id")
    assert compare_predictions(item).dataset_sha256 != first.dataset_sha256


def test_tiny_positive_thresholds_and_zero_tolerance_are_not_lost_to_absolute_epsilon() -> None:
    identical = request(
        "classification-improvement",
        csv_text="actual,baseline,candidate\n" + "a,a,a\n" * 30,
        minimum_improvement=1e-13,
    )
    assert compare_predictions(identical).decision == "rejected"
    small_error = request(
        "regression-improvement",
        task="regression",
        maximum_slice_regression=0,
        csv_text="actual,baseline,candidate,cohort\n"
        + "0,0.2,0,majority\n" * 90
        + "0,0,1e-14,minority\n" * 10,
    )
    result = compare_predictions(small_error)
    assert result.improvement > 0.01
    assert result.decision == "rejected"
    assert next(item for item in result.slices if item.name == "minority").passed is False


def test_renaming_ids_or_reordering_rows_cannot_change_the_uncertainty_estimate() -> None:
    item = request("hidden-regression")
    first = compare_predictions(item)
    header, *rows = item.csv_text.splitlines()
    item.csv_text = header + "\n" + "\n".join(reversed(rows)).replace("desktop-", "sample-") + "\n"
    reordered = compare_predictions(item)
    assert reordered.dataset_sha256 != first.dataset_sha256
    assert reordered.bootstrap_input_sha256 == first.bootstrap_input_sha256
    assert reordered.improvement_interval == first.improvement_interval
    assert reordered.decision == first.decision
