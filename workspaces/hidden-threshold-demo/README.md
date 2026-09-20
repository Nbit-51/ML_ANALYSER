# Hidden Threshold Failure Demo

This small, deterministic fixture demonstrates the evidence loop without expensive training or untrusted code execution.

The saved validation predictions use a baseline decision threshold of `0.5`. That threshold preserves recall but creates several false positives. The ML threshold adapter tests the falsifiable hypothesis that calibration—not model weights—is limiting F1, performs a score-derived threshold sweep, checks the F1 objective and recall guardrail, and records the result in the evidence ledger and experiment DAG.

The fixture is deliberately tiny so the complete loop is fast, reproducible, and suitable for tests and hackathon demonstrations. It is not presented as proof that threshold calibration solves arbitrary ML projects.
