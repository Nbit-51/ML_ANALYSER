"""Count real redundant computations under a fixed workload, and time the harness."""

import json
import time
from pathlib import Path

config = json.loads(Path("config.json").read_text())
started = time.perf_counter()
operations = 0
checksum = 0
for _ in range(config["repeats"]):
    checksum = sum(n * n for n in range(1000))
    operations += 1
if config.get("incorrect"):
    checksum += 1
print(
    json.dumps(
        {
            "metrics": [
                {"name": "work_units", "value": operations, "unit": "operations"},
                {"name": "checks_passed", "value": float(checksum == 332833500), "unit": "ratio"},
                {
                    "name": "elapsed_ms",
                    "value": (time.perf_counter() - started) * 1000,
                    "unit": "ms",
                },
            ],
            "correctness": str(checksum),
        }
    )
)
