"""Recompute an exported prediction report against its original CSV, without inference."""

import argparse
from pathlib import Path

from ml_analyser.evaluation.predictions import (
    PredictionReport,
    PredictionRequest,
    compare_predictions,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("csv", type=Path)
    args = parser.parse_args()
    recorded = PredictionReport.model_validate_json(args.report.read_text(encoding="utf-8"))
    request = PredictionRequest(
        task=recorded.task,
        primary_metric=recorded.primary_metric,
        csv_text=args.csv.read_text(encoding="utf-8"),
        minimum_improvement=recorded.minimum_improvement,
        maximum_slice_regression=recorded.maximum_slice_regression,
        minimum_slice_size=recorded.minimum_slice_size,
    )
    actual = compare_predictions(request)
    if actual != recorded:
        print("Replay failed: CSV, rules, measurements or implementation differ.")
        return 1
    print(
        f"Replay passed: {actual.rows} paired rows, {actual.decision}; metrics and digests match."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"Replay failed: {error}")
        raise SystemExit(1) from None
