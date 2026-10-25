"""Recompute a downloaded lab evidence capsule without a model or API key."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml_analyser.lab.engine import replay


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capsule", type=Path)
    args = parser.parse_args()
    try:
        if args.capsule.stat().st_size > 2_000_000:
            raise ValueError("Capsule exceeds 2 MB.")
        errors = replay(json.loads(args.capsule.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"FAIL: malformed evidence capsule ({type(error).__name__}).")
        return 1
    if errors:
        for error in errors:
            print("FAIL:", error)
        return 1
    print("PASS: commitment, source, negative control, every attempt and winner replay exactly.")
    print("This verifies benchmark evidence consistency, not independent authenticity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
