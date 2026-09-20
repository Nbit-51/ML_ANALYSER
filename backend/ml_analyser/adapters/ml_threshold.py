"""Safe ML classification threshold-calibration adapter."""

from __future__ import annotations

import csv
from hashlib import sha256
from pathlib import Path

from pydantic import Field, field_validator

from ml_analyser.agent.models import StrictModel

MANIFEST_NAME = "ml_analyser.json"


class AdapterValidationError(ValueError):
    """Raised when an adapter project cannot be measured safely."""


class ClassificationManifest(StrictModel):
    adapter: str
    predictions_file: str
    label_column: str = "label"
    score_column: str = "score"
    baseline_threshold: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("adapter")
    @classmethod
    def adapter_must_match(cls, adapter: str) -> str:
        if adapter != "ml_classification_threshold":
            raise ValueError("adapter must be 'ml_classification_threshold'")
        return adapter


class PredictionRow(StrictModel):
    label: int
    score: float

    @field_validator("label")
    @classmethod
    def label_must_be_binary(cls, label: int) -> int:
        if label not in {0, 1}:
            raise ValueError("labels must be binary (0 or 1)")
        return label

    @field_validator("score")
    @classmethod
    def score_must_be_probability(cls, score: float) -> float:
        if not 0.0 <= score <= 1.0:
            raise ValueError("scores must be between 0 and 1")
        return score


class ThresholdObservation(StrictModel):
    threshold: float
    sample_count: int = Field(ge=1)
    true_positives: int = Field(ge=0)
    false_positives: int = Field(ge=0)
    true_negatives: int = Field(ge=0)
    false_negatives: int = Field(ge=0)
    metrics: dict[str, float]


class ClassificationThresholdAdapter:
    """Measure classification predictions without importing target project code."""

    name = "ml_classification_threshold"
    supported_metrics = frozenset({"accuracy", "f1", "precision", "recall"})

    def load(self, project_root: Path) -> tuple[ClassificationManifest, list[PredictionRow]]:
        root = project_root.resolve(strict=True)
        manifest_path = root / MANIFEST_NAME
        if not manifest_path.is_file():
            raise AdapterValidationError(f"missing required manifest: {MANIFEST_NAME}")

        try:
            manifest = ClassificationManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as error:
            raise AdapterValidationError(f"invalid {MANIFEST_NAME}: {error}") from error

        try:
            predictions_path = (root / manifest.predictions_file).resolve(strict=True)
        except OSError as error:
            raise AdapterValidationError(f"cannot resolve predictions_file: {error}") from error
        try:
            predictions_path.relative_to(root)
        except ValueError as error:
            raise AdapterValidationError(
                "predictions_file must stay inside the project directory"
            ) from error
        if not predictions_path.is_file():
            raise AdapterValidationError("predictions_file must identify a file")

        rows: list[PredictionRow] = []
        try:
            with predictions_path.open("r", encoding="utf-8", newline="") as file_handle:
                reader = csv.DictReader(file_handle)
                required = {manifest.label_column, manifest.score_column}
                if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                    raise AdapterValidationError(
                        f"predictions file must contain columns: {sorted(required)}"
                    )
                for line_number, row in enumerate(reader, start=2):
                    try:
                        rows.append(
                            PredictionRow(
                                label=int(row[manifest.label_column]),
                                score=float(row[manifest.score_column]),
                            )
                        )
                    except (TypeError, ValueError) as error:
                        raise AdapterValidationError(
                            f"invalid prediction at CSV line {line_number}: {error}"
                        ) from error
        except OSError as error:
            raise AdapterValidationError(f"cannot read predictions: {error}") from error

        if len(rows) < 2:
            raise AdapterValidationError("at least two prediction rows are required")
        if len({row.label for row in rows}) < 2:
            raise AdapterValidationError("both binary label classes must be present")
        return manifest, rows

    @staticmethod
    def measure(rows: list[PredictionRow], threshold: float) -> ThresholdObservation:
        true_positives = false_positives = true_negatives = false_negatives = 0
        for row in rows:
            predicted = int(row.score >= threshold)
            if predicted == 1 and row.label == 1:
                true_positives += 1
            elif predicted == 1 and row.label == 0:
                false_positives += 1
            elif predicted == 0 and row.label == 0:
                true_negatives += 1
            else:
                false_negatives += 1

        precision_denominator = true_positives + false_positives
        recall_denominator = true_positives + false_negatives
        precision = true_positives / precision_denominator if precision_denominator else 0.0
        recall = true_positives / recall_denominator if recall_denominator else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        accuracy = (true_positives + true_negatives) / len(rows)

        return ThresholdObservation(
            threshold=threshold,
            sample_count=len(rows),
            true_positives=true_positives,
            false_positives=false_positives,
            true_negatives=true_negatives,
            false_negatives=false_negatives,
            metrics={
                "accuracy": accuracy,
                "f1": f1,
                "precision": precision,
                "recall": recall,
            },
        )

    def find_best_threshold(
        self,
        rows: list[PredictionRow],
        *,
        objective_metric: str,
    ) -> ThresholdObservation:
        if objective_metric not in self.supported_metrics:
            raise AdapterValidationError(
                f"unsupported objective metric '{objective_metric}'; supported metrics: "
                f"{sorted(self.supported_metrics)}"
            )

        scores = sorted({row.score for row in rows})
        thresholds = {0.0, 0.5, 1.0}
        thresholds.update(scores)
        thresholds.update(
            (left + right) / 2 for left, right in zip(scores, scores[1:], strict=False)
        )
        observations = [self.measure(rows, threshold) for threshold in sorted(thresholds)]
        return max(
            observations,
            key=lambda item: (
                item.metrics[objective_metric],
                item.metrics["recall"],
                -abs(item.threshold - 0.5),
            ),
        )

    @staticmethod
    def predictions_hash(project_root: Path, manifest: ClassificationManifest) -> str:
        path = (project_root.resolve(strict=True) / manifest.predictions_file).resolve(strict=True)
        digest = sha256()
        with path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
