"""Deterministic sample summaries and transparent comparison reliability rules."""

import platform
import statistics
import sys
from hashlib import sha256

from ml_analyser.agent.models import BenchmarkReliability, Measurement, SampleSummary


def environment_fingerprint() -> str:
    identity = (platform.node(), platform.platform(), platform.machine(), sys.version)
    return sha256(repr(identity).encode()).hexdigest()


def summarize(samples: list[float]) -> SampleSummary:
    if not samples:
        raise ValueError("cannot summarize empty samples")
    ordered = sorted(samples)

    def percentile(p: float) -> float:
        index = (len(ordered) - 1) * p
        lower = int(index)
        upper = min(lower + 1, len(ordered) - 1)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)

    mean = statistics.mean(ordered)
    deviation = statistics.stdev(ordered) if len(ordered) > 1 else 0.0
    return SampleSummary(
        count=len(ordered),
        mean=mean,
        median=statistics.median(ordered),
        minimum=ordered[0],
        maximum=ordered[-1],
        p50=percentile(0.5),
        p90=percentile(0.9),
        p95=percentile(0.95),
        p99=percentile(0.99),
        standard_deviation=deviation,
        coefficient_of_variation=deviation / abs(mean) if mean else None,
    )


def assess_reliability(
    baseline: list[Measurement],
    candidate: list[Measurement],
    required: set[str],
    minimum_samples: int = 3,
    maximum_cv: float = 0.30,
) -> BenchmarkReliability:
    reasons: list[str] = []
    compatible: bool | None = None
    left = {m.metric: m for m in baseline}
    right = {m.metric: m for m in candidate}
    assessed = False
    for name in sorted(required & left.keys() & right.keys()):
        a, b = left[name], right[name]
        if a.unit != b.unit:
            reasons.append(f"{name}: incompatible units")
        if not (a.raw_samples or b.raw_samples or a.failed_sample_count or b.failed_sample_count):
            continue
        assessed = True
        match = bool(a.environment_fingerprint) and (
            a.environment_fingerprint == b.environment_fingerprint
        )
        compatible = match if compatible is None else compatible and match
        if not match:
            reasons.append(f"{name}: environment mismatch or missing fingerprint")
        for label, measurement in (("baseline", a), ("candidate", b)):
            samples = measurement.reliability_samples or measurement.raw_samples
            if len(samples) < minimum_samples:
                reasons.append(f"{name} {label}: insufficient samples ({len(samples)})")
            if measurement.failed_sample_count:
                reasons.append(f"{name} {label}: failed measurements")
            if samples:
                summary = summarize(samples)
                cv = summary.coefficient_of_variation
                if (cv is not None and cv > maximum_cv) or (
                    cv is None and summary.standard_deviation > 0
                ):
                    reasons.append(f"{name} {label}: high variance")
    return BenchmarkReliability(
        status="inconclusive" if reasons else "reliable" if assessed else "not_assessed",
        reasons=reasons,
        minimum_samples=minimum_samples,
        maximum_cv=maximum_cv,
        environment_compatible=compatible,
    )
