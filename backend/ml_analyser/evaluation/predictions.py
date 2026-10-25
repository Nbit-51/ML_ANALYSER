"""Paired prediction metrics, cohort guardrails and reproducible uncertainty estimates."""

from __future__ import annotations

import csv
import hashlib
import io
import math
import random
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import Field

from ml_analyser.agent.ids import canonical_json
from ml_analyser.agent.models import StrictModel

PROTOCOL = "prediction-comparison/v1"
MAX_ROWS = 5_000
BOOTSTRAP_ROUNDS = 200


class PredictionRequest(StrictModel):
    task: Literal["classification", "regression"]
    csv_text: str = Field(min_length=1, max_length=2_000_000)
    primary_metric: Literal["f1_macro", "accuracy", "rmse", "mae"]
    minimum_improvement: float = Field(default=0.01, ge=0, le=1e12, strict=True)
    maximum_slice_regression: float = Field(default=0.02, ge=0, le=1e12, strict=True)
    minimum_slice_size: int = Field(default=10, ge=5, le=1_000, strict=True)


class SliceCheck(StrictModel):
    name: str
    kind: Literal["cohort", "class"]
    metric: str
    count: int
    baseline: float
    candidate: float
    regression: float
    allowed_regression: float
    checked: bool
    passed: bool | None


class PredictionReport(StrictModel):
    protocol: str = PROTOCOL
    source_sha256: str
    dataset_sha256: str
    bootstrap_input_sha256: str
    task: Literal["classification", "regression"]
    primary_metric: Literal["f1_macro", "accuracy", "rmse", "mae"]
    direction: Literal["maximize", "minimize"]
    rows: int
    baseline: dict[str, float | None]
    candidate: dict[str, float | None]
    improvement: float
    improvement_interval: tuple[float, float]
    bootstrap_rounds: int
    minimum_improvement: float
    maximum_slice_regression: float
    minimum_slice_size: int
    slices: list[SliceCheck]
    labels: list[str]
    confusion_matrices: dict[str, list[list[int]]]
    decision: Literal["accepted", "rejected", "inconclusive"]
    reasons: list[str]
    limitations: list[str]
    report_sha256: str = ""


Row = tuple[str | float, str | float, str | float, str]


def _parse(request: PredictionRequest) -> tuple[list[Row], list[str]]:
    if len(request.csv_text.encode("utf-8")) > 2_000_000:
        raise ValueError("CSV must be at most 2 MB of UTF-8 data.")
    reader = csv.reader(io.StringIO(request.csv_text.lstrip("\ufeff")), strict=True)
    try:
        headers = [item.strip() for item in next(reader)]
        if len(set(headers)) != len(headers):
            raise ValueError("CSV column names must be unique.")
        required = {"actual", "baseline", "candidate"}
        if not required.issubset(headers) or set(headers) - required - {"id", "cohort"}:
            raise ValueError("Use actual,baseline,candidate columns; id and cohort are optional.")
        rows: list[Row] = []
        identifiers: set[str] = set()
        labels: set[str] = set()
        cohorts: set[str] = set()
        for number, values in enumerate(reader, start=2):
            if not values:
                continue
            if len(rows) >= MAX_ROWS:
                raise ValueError(f"CSV is limited to {MAX_ROWS:,} rows.")
            if len(values) != len(headers) or any(len(value) > 160 for value in values):
                raise ValueError(f"CSV row {number} has missing/extra cells or an oversized value.")
            record = dict(zip(headers, (value.strip() for value in values), strict=True))
            if any(not value for value in record.values()):
                raise ValueError(f"CSV row {number} contains an empty value.")
            if "id" in record:
                if record["id"] in identifiers:
                    raise ValueError(f"CSV row {number} repeats a sample id.")
                identifiers.add(record["id"])
            cohort = record.get("cohort", "All samples")
            cohorts.add(cohort)
            if len(cohorts) > 20:
                raise ValueError("Use at most 20 cohorts.")
            predictions: list[str | float] = []
            for key in ("actual", "baseline", "candidate"):
                value: str | float = record[key]
                if request.task == "regression":
                    try:
                        value = float(value)
                    except ValueError as error:
                        raise ValueError(f"CSV row {number}: {key} must be numeric.") from error
                    if not math.isfinite(value) or abs(value) > 1e12:
                        raise ValueError(
                            f"CSV row {number}: numeric values must be finite and ≤ 1e12."
                        )
                else:
                    labels.add(str(value))
                    if len(labels) > 20:
                        raise ValueError("Use at most 20 classification labels.")
                predictions.append(value)
            rows.append((predictions[0], predictions[1], predictions[2], cohort))
    except (csv.Error, StopIteration) as error:
        raise ValueError("CSV is empty or malformed.") from error
    if len(rows) < 2:
        raise ValueError("Provide at least two paired prediction rows.")
    return rows, sorted(labels)


def _classification(rows: list[Row], index: int, labels: list[str]) -> dict[str, float | None]:
    counts = Counter((row[0], row[index]) for row in rows)
    actual = Counter(row[0] for row in rows)
    predicted = Counter(row[index] for row in rows)
    precision, recall, f1, weighted = 0.0, 0.0, 0.0, 0.0
    for label in labels:
        true = counts[label, label]
        p = true / predicted[label] if predicted[label] else 0.0
        r = true / actual[label] if actual[label] else 0.0
        f = (
            2 * true / (actual[label] + predicted[label])
            if actual[label] + predicted[label]
            else 0.0
        )
        precision += p
        recall += r
        f1 += f
        weighted += f * actual[label]
    return {
        "accuracy": sum(counts[label, label] for label in labels) / len(rows),
        "precision_macro": precision / len(labels),
        "recall_macro": recall / len(labels),
        "f1_macro": f1 / len(labels),
        "f1_weighted": weighted / len(rows),
    }


def _regression(rows: list[Row], index: int) -> dict[str, float | None]:
    errors = [float(row[index]) - float(row[0]) for row in rows]
    mse = math.fsum(error * error for error in errors) / len(rows)
    mean = math.fsum(float(row[0]) for row in rows) / len(rows)
    variance = math.fsum((float(row[0]) - mean) ** 2 for row in rows) / len(rows)
    r2 = 1 - mse / variance if variance else None
    return {
        "mae": math.fsum(abs(error) for error in errors) / len(rows),
        "rmse": math.sqrt(mse),
        "r2": r2 if r2 is not None and math.isfinite(r2) else None,
    }


def _metrics(rows: list[Row], index: int, labels: list[str]) -> dict[str, float | None]:
    return _classification(rows, index, labels) if labels else _regression(rows, index)


def _primary(rows: list[Row], index: int, labels: list[str], metric: str) -> float:
    value = _metrics(rows, index, labels)[metric]
    assert value is not None
    return value


def _at_least(value: float, minimum: float) -> bool:
    return value >= minimum or math.isclose(value, minimum, rel_tol=1e-12, abs_tol=0)


def _slice_checks(
    request: PredictionRequest, rows: list[Row], labels: list[str]
) -> list[SliceCheck]:
    checks = []
    for cohort in sorted({row[3] for row in rows}):
        selected = [row for row in rows if row[3] == cohort]
        metric = "accuracy" if labels else "mae"
        before = _primary(selected, 1, labels, metric)
        after = _primary(selected, 2, labels, metric)
        regression = before - after if labels else after - before
        checked = len(selected) >= request.minimum_slice_size
        checks.append(
            SliceCheck(
                name=cohort,
                kind="cohort",
                metric=metric,
                count=len(selected),
                baseline=before,
                candidate=after,
                regression=regression,
                allowed_regression=request.maximum_slice_regression,
                checked=checked,
                passed=_at_least(request.maximum_slice_regression, regression) if checked else None,
            )
        )
    for label in labels:
        selected = [row for row in rows if row[0] == label]
        if not selected:
            continue
        before = sum(row[1] == label for row in selected) / len(selected)
        after = sum(row[2] == label for row in selected) / len(selected)
        checked = len(selected) >= request.minimum_slice_size
        checks.append(
            SliceCheck(
                name=label,
                kind="class",
                metric="recall",
                count=len(selected),
                baseline=before,
                candidate=after,
                regression=before - after,
                allowed_regression=request.maximum_slice_regression,
                checked=checked,
                passed=_at_least(request.maximum_slice_regression, before - after)
                if checked
                else None,
            )
        )
    return checks


def compare_predictions(request: PredictionRequest) -> PredictionReport:
    classification = request.task == "classification"
    if request.primary_metric not in (
        {"f1_macro", "accuracy"} if classification else {"rmse", "mae"}
    ):
        raise ValueError("Choose a primary metric compatible with the selected task.")
    if classification and (request.minimum_improvement > 1 or request.maximum_slice_regression > 1):
        raise ValueError("Classification improvements and tolerances use the 0–1 scale.")
    rows, labels = _parse(request)
    before, after = _metrics(rows, 1, labels), _metrics(rows, 2, labels)
    sign = 1 if classification else -1
    improvement = sign * (
        _primary(rows, 2, labels, request.primary_metric)
        - _primary(rows, 1, labels, request.primary_metric)
    )
    canonical_csv = request.csv_text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    data_hash = hashlib.sha256(canonical_csv.encode()).hexdigest()
    sampling_rows: list[Row] = sorted(
        [(row[0], row[1], row[2], "") for row in rows], key=canonical_json
    )
    bootstrap_hash = hashlib.sha256(canonical_json(sampling_rows).encode()).hexdigest()
    generator = random.Random(int(bootstrap_hash, 16))
    deltas = []
    for _ in range(BOOTSTRAP_ROUNDS):
        sample = [sampling_rows[generator.randrange(len(rows))] for _ in rows]
        deltas.append(
            sign
            * (
                _primary(sample, 2, labels, request.primary_metric)
                - _primary(sample, 1, labels, request.primary_metric)
            )
        )
    deltas.sort()
    interval = (deltas[4], deltas[194])
    slices = _slice_checks(request, rows, labels)
    failed = [item for item in slices if item.passed is False]
    reasons = []
    decision: Literal["accepted", "rejected", "inconclusive"]
    if failed or not _at_least(improvement, request.minimum_improvement):
        decision = "rejected"
        if failed:
            reasons.append(
                "Regression limit failed: " + ", ".join(f"{s.kind} {s.name}" for s in failed)
            )
        if not _at_least(improvement, request.minimum_improvement):
            reasons.append("Overall improvement is below the configured minimum.")
    elif len(rows) < 20 or any(not item.checked for item in slices):
        decision = "inconclusive"
        reasons.append("Need at least 20 paired rows and the minimum support in each cohort/class.")
    elif not _at_least(interval[0], request.minimum_improvement):
        decision = "inconclusive"
        reasons.append("The paired bootstrap interval crosses the required improvement.")
    else:
        decision = "accepted"
        reasons.append("Overall improvement, bootstrap lower bound and every supported slice pass.")
    matrices = {}
    if labels:
        for name, index in (("baseline", 1), ("candidate", 2)):
            counts = Counter((row[0], row[index]) for row in rows)
            matrices[name] = [
                [counts[actual, predicted] for predicted in labels] for actual in labels
            ]
    report = PredictionReport(
        source_sha256=hashlib.sha256(
            Path(__file__).read_text(encoding="utf-8").encode()
        ).hexdigest(),
        dataset_sha256=data_hash,
        bootstrap_input_sha256=bootstrap_hash,
        task=request.task,
        primary_metric=request.primary_metric,
        direction="maximize" if classification else "minimize",
        rows=len(rows),
        baseline=before,
        candidate=after,
        improvement=improvement,
        improvement_interval=interval,
        bootstrap_rounds=BOOTSTRAP_ROUNDS,
        minimum_improvement=request.minimum_improvement,
        maximum_slice_regression=request.maximum_slice_regression,
        minimum_slice_size=request.minimum_slice_size,
        slices=slices,
        labels=labels,
        confusion_matrices=matrices,
        decision=decision,
        reasons=reasons,
        limitations=[
            "Evaluates supplied predictions; no model training, repository code or inference ran.",
            "Approximate 95% paired percentile bootstrap; 200 resamples with independent rows.",
            "Correlations, dataset leakage and population representativeness are not verified.",
            "Slice checks are guardrails, not proof of fairness or statistical significance.",
            "Undefined precision/recall/F1 use zero; R² is null for constant targets.",
            "No model latency, compute cost, causality or future performance is measured.",
        ],
    )
    report.report_sha256 = hashlib.sha256(
        canonical_json(report.model_dump(mode="json")).encode()
    ).hexdigest()
    return report
