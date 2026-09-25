# Demonstration guide

## Demo thesis

AI coding assistants are good at proposing changes. ML Analyser treats every proposal as a hypothesis until measurement proves it helped.

The primary measured demonstration uses a small binary-classification training repository with an underpowered baseline configuration. The general preview accepts other ML repository types and user-defined metrics; it is read-only until an adapter explicitly supports execution. A separate saved-prediction threshold fixture remains available as a faster evidence-loop example.

## General ML repository preview

Place a local checkout under `workspaces/`. In the first section of `/app`, enter its relative folder name, choose the metric to improve, its direction, and any target or guardrail. The interface explains common scores in plain language, displays prior values with source paths, and distinguishes proposals from measured results. You can inspect any local ML repository here; the preview does not run its scripts or train a model.

For example, the public [Leaf repository](https://github.com/Nbit-51/Leaf) is an inference-engine project rather than a classifier-training project. Clone it into `workspaces/leaf`, set the objective to `leaf_cpp_fp32_p50_ms` with **minimize**, and optionally protect `leaf_cpp_vs_pytorch_max_abs` with an **at-most** limit. A live Nemotron preview in the browser completed on September 25, 2026. It found two existing CIFAR-10/ResNet-18 benchmark records: prior median latencies **9.4825 ms** and **9.701 ms**, and maximum absolute difference about **4.62e-7**. These are values recorded by Leaf, not measurements performed by ML Analyser. A beginner can infer that lower median latency is desirable only if numerical agreement stays within the chosen guardrail and the workload, hardware, and measurement procedure remain comparable.

The generated hypotheses are suggestions to verify, not established code facts. Source excerpts are partial; inspect the full cited file before applying a proposed change. No Leaf benchmark was executed or modified by this preview.

## Primary browser walkthrough

Start the API with `uvicorn ml_analyser.main:app --app-dir backend --reload` and open `http://127.0.0.1:8000/app`.

1. Select **ML training** and inspect the displayed F1 objective, recall/accuracy guardrails, and 10-second budget.
2. Select **Inspect & prepare experiment**. Preparation inventories the fixture and exposes the hypothesis, configuration override, rejection rule, and approval risk. No target code runs yet.
3. Select **Approve exact plan & start**. The approval is bound to the plan fingerprint and can be consumed once.
4. Follow the persisted state timeline while the baseline and candidate copies train and evaluate.
5. Inspect measured F1/accuracy/recall, the decision reason, evidence IDs, baseline-to-candidate lineage, and the retained candidate disposition.
6. Repeat with **Backend benchmark** to show that the same approval, objective, guardrail, evidence, and decision machinery applies outside ML.

The training fixture's observed baseline F1 is **0.6667** and candidate F1 is **1.0000**. Accuracy rises from **0.5000** to **1.0000**; recall remains **1.0000**. These values are emitted by `train.py` after real local evaluation and asserted in tests. The original fixture is unchanged. This is a controlled workflow proof on a tiny dataset, not evidence of broad model generalization.

## Saved-prediction threshold example

## Success contract

```yaml
objective:
  metric: f1
  direction: maximize
  minimum_improvement: 0.01
constraints:
  recall: ">= 0.8"
budget:
  wall_clock_seconds: 30
  max_experiments: 2
```

The committed machine-readable request is in `workspaces/hidden-threshold-demo/request.json`.

## Run it

Start the API:

```bash
uvicorn ml_analyser.main:app --app-dir backend --reload
```

In another terminal:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/runs/ml-threshold-demo \
  -H "Content-Type: application/json" \
  --data @workspaces/hidden-threshold-demo/request.json
```

Omitting `"approved": true` returns HTTP `409`, demonstrating the approval boundary.

## What the audience should notice

1. The agent inventories the project and builds a deterministic state graph.
2. The mock reasoning provider proposes a falsifiable calibration hypothesis.
3. The experiment is linked to a baseline node in the experiment DAG.
4. The adapter measures the same saved validation set at baseline and candidate thresholds.
5. Deterministic application code—not the model—evaluates the objective, recall guardrail, and budget.
6. The decision, evidence, and experiment lineage are persisted to SQLite.
7. No project code or training script is imported or executed.

## Reproducible observed result

| Measurement | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| Threshold | 0.5000 | 0.5950 | +0.0950 |
| F1 | 0.7692 | 0.9091 | +0.1399 |
| Precision | 0.6250 | 0.8333 | +0.2083 |
| Recall | 1.0000 | 1.0000 | 0.0000 |
| Accuracy | 0.7000 | 0.9000 | +0.2000 |

Decision: **accepted**. The F1 improvement exceeds `0.01`, recall remains above `0.8`, and the experiment stays within budget.

These values are calculated from the committed `validation_predictions.csv` fixture and asserted by automated tests. They are not invented by the mock provider or copied into the decision path.

## Suggested three-minute narrative

1. **Problem:** “Most agents say they improved a project after changing code. We require measurable proof.”
2. **Contract:** Show the F1 objective, recall guardrail, and experiment/time budget.
3. **Hypothesis:** Show that the system identifies threshold calibration as a cheap diagnostic before retraining.
4. **Execution:** Submit the approved request and point out the explicit lifecycle states.
5. **Evidence:** Compare confusion counts and metrics, then inspect evidence IDs and the parent experiment.
6. **Decision:** Show why the candidate was accepted and where the run was persisted.
7. **Reasoning:** Show the live Nemotron preview separately from the measured fixture. Deterministic policies still retain authority over safety and acceptance.

## Honest limitations

- This is a narrow threshold-calibration adapter over saved binary-classification predictions.
- The primary ML adapter runs a declared training script; arbitrary commands and patch generation remain unsupported.
- The mock provider is rule-based and offline; the separately validated live preview uses Nebius/Nemotron but does not perform the measured fixture run.
- The state graph currently models repository/category/file provenance, not parsed code semantics.
- The SQLite store and process-local background tasks are appropriate for the local workbench, not distributed experiment workers.

Those limits are intentional. The demo proves the evidence loop before the project expands its execution surface.
