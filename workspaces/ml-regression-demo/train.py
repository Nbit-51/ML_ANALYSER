import argparse
import json
import math
from pathlib import Path
from time import perf_counter

p = argparse.ArgumentParser()
p.add_argument("--config")
p.add_argument("--output")
a = p.parse_args()
started = perf_counter()
bias = json.loads(Path(a.config).read_text())["bias"]
actual = [1, 2, 3, 4]
predicted = [value + bias for value in actual]
rmse = math.sqrt(sum((a - b) ** 2 for a, b in zip(actual, predicted, strict=True)) / len(actual))
Path(a.output).write_text(
    json.dumps(
        {
            "metrics": {"validation_rmse": rmse},
            "sample_count": len(actual),
            "duration_seconds": perf_counter() - started,
        }
    )
)
