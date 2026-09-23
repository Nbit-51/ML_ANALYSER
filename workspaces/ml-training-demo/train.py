"""Small reproducible logistic regression project using only the standard library."""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from pathlib import Path


def read_rows(path: Path) -> list[tuple[float, int]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [(float(row["x"]), int(row["label"])) for row in csv.DictReader(handle)]


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def train(rows: list[tuple[float, int]], epochs: int, learning_rate: float) -> tuple[float, float]:
    weight = bias = 0.0
    for _ in range(epochs):
        weight_gradient = bias_gradient = 0.0
        for feature, label in rows:
            error = sigmoid(weight * feature + bias) - label
            weight_gradient += error * feature
            bias_gradient += error
        weight -= learning_rate * weight_gradient / len(rows)
        bias -= learning_rate * bias_gradient / len(rows)
    return weight, bias


def evaluate(rows: list[tuple[float, int]], weight: float, bias: float) -> dict[str, float]:
    tp = fp = tn = fn = 0
    for feature, label in rows:
        predicted = int(sigmoid(weight * feature + bias) >= 0.5)
        if predicted and label:
            tp += 1
        elif predicted:
            fp += 1
        elif label:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "accuracy": (tp + tn) / len(rows),
        "f1": f1,
        "precision": precision,
        "recall": recall,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    here = Path(__file__).resolve().parent
    training = read_rows(here / "train.csv")
    validation = read_rows(here / "validation.csv")
    weight, bias = train(training, int(config["epochs"]), float(config["learning_rate"]))
    result = {
        "metrics": evaluate(validation, weight, bias),
        "sample_count": len(validation),
        "duration_seconds": time.perf_counter() - started,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
