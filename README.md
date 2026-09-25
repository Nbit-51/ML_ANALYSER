# ML Analyser

ML Analyser is an evidence-driven agent for analyzing and improving ML repositories across tasks such as classification, regression, and inference benchmarking. Users define the metric that matters to their project; the analyzer does not assume every repository trains a classifier or reports F1. A small backend benchmark adapter demonstrates that the verification engine is reusable beyond ML.

It diagnoses technical failures, turns explanations into falsifiable hypotheses, compiles controlled experiments, executes bounded tools, and retains changes only when recorded evidence supports them.

> Status: the local ML training and backend benchmark workflows support plan review, fingerprint-bound single-use approval, isolated baseline/candidate execution, measured decisions, and persisted evidence. General repository preview works with the mock provider or NVIDIA Nemotron through Nebius Token Factory. A live read-only Nemotron preview was validated through the browser on September 25, 2026; arbitrary ML repositories are not yet executable by the local adapters.

## What works today

- `POST /api/v1/runs/preview` inventories a project inside `workspaces/`, builds its state graph, samples bounded README/source/prior-result evidence, proposes falsifiable hypotheses with the selected model provider, and compiles non-executed experiment specifications. With the default mock provider, proposals are deterministic.
- `POST /api/v1/runs/ml-threshold-demo` requires explicit approval, measures saved binary-classification predictions, performs a deterministic threshold sweep, evaluates the objective, recall guardrail, and budget, then persists evidence and experiment lineage to SQLite.
- `POST /api/v1/runs/backend-benchmark/prepare` creates a complete experiment plan and a persisted approval bound to the plan's canonical fingerprint.
- `POST /api/v1/runs/approvals/{approval_id}` approves or rejects exactly one pending scope. An approved scope is single-use; changed plans and replay attempts are rejected.
- `POST /api/v1/runs/backend-benchmark/execute` copies the source into isolated baseline and candidate workspaces, applies only manifest-declared JSON overrides, runs a bounded localhost benchmark, evaluates objective/guardrails/budget, and retains or discards the candidate without modifying the source.
- `POST /api/v1/runs/ml-training/prepare` and `/ml-training/execute` perform the same approved evidence loop for a declared Python training entrypoint and JSON configuration. The adapter measures actual validation metrics emitted by the script, not model-generated estimates.
- `POST /api/v1/runs/ml-training/start` and `/backend-benchmark/start` launch local background runs; `GET /api/v1/runs/live/{run_id}` exposes persisted progress events and results. The browser workbench is available at `/app`.
- The lifecycle rejects illegal stage transitions, unknown schema fields are rejected, project paths cannot escape the configured workspace, and preview mode never imports or executes target repository code.
- The mock provider is deterministic and offline. The real Nebius provider is disabled by default, requests structured JSON, and rejects malformed or ungrounded responses. Nebius/Nemotron is never silently simulated.

The included hidden-failure fixture proves the loop on a deliberately miscalibrated classifier:

| Measurement | Baseline (`0.5`) | Candidate (`0.595`) |
| --- | ---: | ---: |
| F1 | 0.7692 | 0.9091 |
| Precision | 0.6250 | 0.8333 |
| Recall | 1.0000 | 1.0000 |
| Accuracy | 0.7000 | 0.9000 |

The candidate passes the `F1 +0.01` objective, `recall >= 0.8` guardrail, and configured experiment budget. These values are computed from the committed validation-prediction fixture; they are not model-generated claims.

The backend fixture provides a second, non-ML proof. In the final local validation on September 21, 2026, P95 latency improved from **50.23 ms** to **22.12 ms**, error rate remained `0`, and baseline/candidate response hashes were identical. The accepted candidate was retained in an isolated workspace and the original project was unchanged. Latency varies by host, so automated tests assert the contract (`candidate P95 < 40 ms` and improvement `> 10 ms`) rather than this one observed value.

The training fixture is a small, deterministic logistic-regression project. On the included data, the baseline produced F1 **0.6667** and accuracy **0.5000**; the approved configuration candidate produced F1 **1.0000** and accuracy **1.0000**, with recall **1.0000** in both cases. The source fixture was unchanged; the accepted configuration remains in an isolated candidate workspace. This fixture demonstrates the workflow, not broad model-quality generalization.

### Reading the scores

A score is meaningful only with its dataset, evaluation procedure, and direction. F1 balances precision and recall (higher is usually better); precision is the share of positive predictions that were correct, while recall is the share of actual positives found. Accuracy is the overall correct-prediction share, but can be misleading on imbalanced data. RMSE summarizes prediction error (lower is better). P50 latency is the median runtime and P95 is the runtime at or below which 95% of measurements finished (lower is better for the same workload). Maximum absolute difference measures the largest output deviation from a reference (smaller means closer agreement). The browser explains these and other common metrics beside the values.

For a beginner, the useful inference is **not** simply “the number changed.” Compare baseline and candidate on the same evaluation setup, check whether the primary goal improved by the required amount, then confirm every guardrail still passes. In read-only preview, a number found in an existing results file is labeled a *prior record*: it can guide a hypothesis, but it does not prove a proposed change worked. Unknown custom metrics require the repository's own definition.

## The problem

Improving a technical system requires more than reviewing source files. An engineer must connect project structure, configuration, runtime evidence, benchmarks, logs, and artifacts. In ML, that also includes datasets, training logic, checkpoints, and evaluation assumptions. Important failures—data leakage, a slow query, misleading metrics, a hidden regression, or irreproducible runs—often appear only when those signals are considered together.

General-purpose coding agents can suggest or implement changes, but “improved” often means only that code was modified and tests still pass. They rarely maintain experiment lineage, choose among tests under a real budget, enforce a machine-readable success contract, or prove a target outcome improved without regressions. They may lose the connection between a recommendation and its evidence, or imply that an experiment happened when it did not.

## Proposed solution

ML Analyser will behave like a skeptical verification engineer rather than a one-shot chatbot. Given a repository, prior runs, a success contract, and a project workspace, it will:

1. construct a **project state graph** connecting datasets, configurations, code, models, checkpoints, metrics, and previous runs;
2. diagnose anomalies and express each proposed cause as a **falsifiable hypothesis**;
3. use an **experiment compiler** to produce a reproducible patch, configuration, command, environment description, and expected measurement;
4. select the next experiment by expected information gain/value, risk, and available budget;
5. execute only approved tools and experiments inside a constrained workspace;
6. capture commands, outputs, errors, metrics, and generated artifacts in an **evidence ledger**;
7. evaluate each candidate against the primary objective and all regression guardrails;
8. accept or reject the hypothesis, keep or safely revert the provisional change, and choose the next experiment from the result; and
9. store lineage in a persistent **experiment DAG** and generate a reproducible final report.

The core product promise is **evidence before claims**. Every AI-generated change is treated as an untrusted hypothesis until measurement supports it. A failed or skipped experiment remains failed or skipped; the system will not fabricate a successful result.

## Why this is more than an LLM wrapper

The model is a reasoning engine inside the product, not the product itself. A normal assistant can read code and recommend “try augmentation” or “lower the learning rate.” ML Analyser must convert that suggestion into a testable claim, run a controlled comparison, check every constraint, and remember the outcome across future runs.

The defensible system is the combination of:

- structured project understanding rather than a repository pasted as text;
- empirical hypothesis testing rather than unverified advice;
- safe, reproducible execution rather than suggested commands;
- objective and constraint-aware experiment selection;
- durable evidence and experiment lineage rather than chat history; and
- an adaptive loop in which experiment N determines experiment N+1.

The model supports reasoning. Execution, lineage, evaluation, and evidence make the recommendations verifiable.

Within ML, the same preview can use a user-specified objective and guardrails for different model types, datasets, and workflows. Controlled execution currently requires a declared adapter; it does not run arbitrary training or benchmark commands. The same core loop also supports different measurable systems through adapters:

| Adapter | Example objective | Example guardrails |
| --- | --- | --- |
| ML (flagship) | Maximize validation F1 | Recall, VRAM, latency, model size |
| Backend benchmark | Reduce P95 API latency | Tests, memory, error rate, throughput |
| AI-agent evaluation (prototype) | Improve task success | Token cost, latency, evaluator score |

The project will not claim to improve every codebase. The core engine owns verification and experimental lineage; each adapter must explicitly define what can be observed, changed, measured, and compared in its domain.

## Agent workflow

```text
Repository + previous runs
  -> Build project state graph
  -> Diagnose anomaly
  -> Generate falsifiable hypotheses
  -> Compile minimal controlled experiments
  -> Rank by information/value, risk, and compute cost
  -> Safety and approval checks
  -> Execute -> measure -> compare with baseline and guardrails
  -> Accept or reject the hypothesis
  -> Update evidence ledger and experiment DAG
  -> Select the next experiment or produce the final report
```

Each run will maintain explicit state. Planning and execution are separate stages, tool calls produce durable evidence records, and report generation consumes those records instead of relying only on model memory. The loop is adaptive rather than a fixed checklist.

### Machine-readable success contracts

A user does not merely ask the agent to “make it better.” Every optimization run begins with an explicit objective, target, constraints, and budget. For example:

```yaml
objective:
  metric: p95_latency_ms
  target: "< 250"
constraints:
  tests_pass_rate: "= 1.0"
  memory_mb: "< 1024"
  error_rate: "< 0.005"
budget:
  wall_clock_minutes: 30
  max_experiments: 8
  max_cost_usd: 5.00
```

A primary-metric improvement that violates any constraint is not accepted. Budgets can cover money, GPU/CPU minutes, model tokens, experiment count, or wall-clock time. Cost estimates and uncertainty must be visible; a predicted cost is never recorded as an actual cost.

### Information gain before expensive changes

The best next action is not always the change most likely to win. When multiple diagnoses are plausible, a cheap discriminating measurement may eliminate more uncertainty than a long training run. The selector will therefore consider expected information gain per unit cost as well as expected improvement. Before expensive execution, Nemotron can fill structured diagnostic, skeptic, experiment-planner, and judge roles; these are review roles in one workflow, not a claim that more agents are inherently better.

### Persistent experiment DAG

Experiments are nodes, not chat messages. Each node will reference its parent experiment and record the code revision, patch, configuration, dataset version, model/checkpoint, hardware, duration, cost, metrics, logs, hypothesis, and conclusion. This allows the agent to understand model lineage, compare compatible runs, avoid repeating disproven ideas, and revisit a hypothesis only when relevant project state changes.

```text
                         baseline
                       /     |      \
                 lower LR  new loss  augmentation
                   +1.8%     -0.6%       +3.2%
                      \                    /
                       LR + augmentation
                              +4.1%
```

## Architecture

The system is organized around six major components:

- **Web application:** a clean, demo-friendly frontend for project intake, run progress, findings, experiment comparisons, and the final report.
- **FastAPI service:** request validation, run lifecycle APIs, artifact access, and streaming/status endpoints.
- **Agent runtime:** a state machine coordinating diagnosis, hypotheses, experiment compilation, guarded execution, evaluation, and reporting.
- **Experiment intelligence:** the project state graph, budget-aware selector, evidence ledger, regression guardrails, and experiment DAG.
- **Domain adapters:** ML first, then a smaller general-software benchmark adapter, with an AI-agent evaluator as a stretch prototype.
- **Provider and tool adapters:** swappable model providers plus constrained repository, test, lint, training, benchmark, and evaluation tools.

```text
Browser UI
    |
FastAPI API
    |
Run service / persistence
    |
Closed-loop orchestrator ---- State graph / evidence ledger
    |            |                         |
Hypothesis -> Experiment compiler -> Experiment DAG
    |                 |                    |
Model provider   Guarded runner ---- Objective/guardrail evaluator
                      |
             Isolated workspace / compute
```

See [Architecture](docs/ARCHITECTURE.md) for component boundaries and run states, [Project context](docs/PROJECT_CONTEXT.md) for current decisions, [Demo guide](docs/DEMO_GUIDE.md) for a reproducible walkthrough, and [Deployment and security](docs/DEPLOYMENT_AND_SECURITY.md) for the execution boundary.

## Technology stack

Current foundation:

- Python 3.11+
- FastAPI
- Pydantic Settings
- Uvicorn
- Pytest and HTTPX
- Ruff and mypy
- SQLite evidence, approval, and experiment-DAG persistence
- Isolated local workspaces and a bounded HTTP benchmark adapter
- A declared Python training adapter and a dependency-free HTML/CSS/JavaScript workbench
- Persisted local run events and polling-based progress

Planned additions:

- production-grade worker scheduling, structured tracing, and streaming progress updates.

## Nebius and NVIDIA integration

The primary reasoning provider uses an **NVIDIA Nemotron open-source model served through Nebius Token Factory**. The model identifier is selected through `NEBIUS_MODEL` rather than hard-coded. Nemotron supports structured diagnosis and experiment planning, while deterministic code enforces schemas, evidence references, budgets, policies, and acceptance rules.

The provider boundary keeps orchestration independent from any one inference API. The implemented Token Factory adapter follows the official [Token Factory quickstart](https://docs.tokenfactory.nebius.com/quickstart) and [structured-output guide](https://docs.tokenfactory.nebius.com/ai-models-inference/json): it calls the OpenAI-compatible chat-completions endpoint, requests JSON-schema output, uses environment-based credentials, and exposes configuration, transport, and validation failures without inventing completions. Contract tests use HTTPX's in-memory transport, so they require no secret or paid request. A live frontend preview succeeded with `nvidia/nemotron-3-super-120b-a12b`; this validates read-only reasoning, not arbitrary project execution.

No API credentials belong in this repository. `.env.example` contains variable names only; local values should be stored in an ignored `.env` file or a deployment secret manager.

When the live provider is enabled, bounded repository excerpts and prior-result records are sent to Nebius as model context. Review privacy requirements before previewing a private repository. Schema and evidence-ID validation do not prove every statement is factually correct; inspect cited source before acting on a proposed intervention.

## Repository layout

```text
.
|-- backend/
|   |-- ml_analyser/
|   |   |-- adapters/       # Domain measurement adapters
|   |   |-- agent/          # Models, ports, lifecycle, evaluator, orchestration
|   |   |-- api/routes/     # HTTP route modules
|   |   |-- core/           # Configuration and cross-cutting concerns
|   |   |-- execution/      # Isolated candidate workspace lifecycle
|   |   |-- persistence/    # SQLite evidence ledger and experiment DAG
|   |   |-- tools/          # Bounded read-only repository tools
|   |   `-- main.py         # FastAPI application factory
|   `-- tests/              # Unit, contract, API, and integration tests
|-- docs/
|   |-- ARCHITECTURE.md
|   |-- BACKEND_BENCHMARK_DEMO.md
|   |-- DEPLOYMENT_AND_SECURITY.md
|   |-- DEMO_GUIDE.md
|   `-- PROJECT_CONTEXT.md
|-- frontend/               # Browser workbench served at /app
|-- scripts/                # Credential-gated live provider validation
|-- workspaces/
|   |-- hidden-threshold-demo/ # Committed deterministic ML fixture
|   |-- backend-benchmark-demo/ # Committed localhost benchmark fixture
|   `-- ml-training-demo/   # Committed training/evaluation fixture
|-- .github/workflows/ci.yml
|-- .env.example
`-- pyproject.toml
```

## Local development

### Prerequisites

- Python 3.11 or newer
- Git

### Setup

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
```

macOS/Linux activation and copy commands are:

```bash
source .venv/bin/activate
cp .env.example .env
```

No external credentials are needed when `ML_ANALYSER_MODEL_PROVIDER=mock`, which is the default. For live Token Factory reasoning, set `ML_ANALYSER_MODEL_PROVIDER=nebius`, `NEBIUS_API_KEY`, and a currently available NVIDIA Nemotron identifier in `NEBIUS_MODEL`. Never commit the local `.env` file.

### Run the API

```bash
uvicorn ml_analyser.main:app --app-dir backend --reload
```

Then open:

- API root: <http://127.0.0.1:8000/>
- health check: <http://127.0.0.1:8000/api/v1/health>
- OpenAPI UI: <http://127.0.0.1:8000/docs>
- browser workbench: <http://127.0.0.1:8000/app>

The workbench uses the mock provider by default. For a general ML repository, place a local checkout inside `workspaces/`, enter its relative folder name and a project-defined objective (for example, F1, validation RMSE, or P50 latency), then select **Analyse repository**. This read-only preview reports inventory, bounded source/prior-result evidence, and proposals; it does not run a new experiment. For a measured run, choose the ML training or backend benchmark fixture, inspect the generated plan and success contract, approve its exact scope, then follow the run timeline and measured decision. Local background tasks are process-bound: restarting the API interrupts active work. For an untrusted uploaded repository, use an external sandbox rather than this local runner.

For the public [Leaf repository](https://github.com/Nbit-51/Leaf), an inference-engine example, clone it locally into `workspaces/leaf` and enter `leaf` in the preview form. Its committed CIFAR-10/ResNet-18 result files report prior `leaf_cpp_fp32_p50_ms` values of **9.4825 ms** and **9.701 ms**, with `leaf_cpp_vs_pytorch_max_abs` around **4.62e-7**. These are repository-recorded results from a particular workload and environment, not scores measured by ML Analyser. In the browser, you can set a lower-is-better latency goal and a maximum-absolute-difference guardrail, then inspect the generated hypotheses. Do not interpret a proposal as an optimization until a compatible benchmark is executed and compared with a baseline.

### Run the hidden-failure demonstration

With the API running, execute:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/runs/ml-threshold-demo \
  -H "Content-Type: application/json" \
  --data @workspaces/hidden-threshold-demo/request.json
```

The JSON response contains the hypothesis, baseline and candidate confusion matrices, exact metrics, state history, evidence records, experiment parentage, deterministic decision, and recommendation. Evidence and DAG nodes are also written to the ignored local database configured by `ML_ANALYSER_STATE_DATABASE`.

### Run the backend benchmark demonstration

The backend proof deliberately uses separate prepare, approve, and execute calls so a reviewer can inspect the complete scope before granting execution. See [Backend benchmark demo](docs/BACKEND_BENCHMARK_DEMO.md) for PowerShell and API examples plus the measured result.

### Validate Token Factory

Set `ML_ANALYSER_MODEL_PROVIDER=nebius`, `NEBIUS_API_KEY`, and a currently available NVIDIA Nemotron ID in `NEBIUS_MODEL`. Then run `python scripts/validate_nebius.py` from the repository root. This performs a read-only preview and validates the returned hypotheses; it does not execute project code. The default request mode is `json_schema`. If the selected model supports JSON-object mode instead, set `ML_ANALYSER_NEBIUS_RESPONSE_FORMAT=json_object` and repeat. No credential value is printed. The live smoke test and browser preview have passed with Nemotron 3 Super. The next step is debugging and validating a separately approved, adapter-supported measured run; preview success alone is not execution proof.

### Quality checks

```bash
pytest
ruff check .
ruff format --check backend
mypy backend/ml_analyser
node --test frontend/metrics.test.js
```

CI additionally enforces at least 90% backend statement coverage.

## Roadmap

- [x] Initialize repository structure and engineering conventions.
- [x] Document project context and target architecture.
- [x] Add a minimal, tested FastAPI service.
- [x] Add CI for tests, linting, and type checking.
- [x] Define typed agent, model-provider, tool, evidence, and run-state interfaces.
- [x] Add a deterministic local/mock model provider.
- [x] Implement bounded repository inventory and a deterministic project state graph.
- [x] Implement falsifiable hypothesis and experiment-compiler schemas.
- [x] Add explicit lifecycle stages and bounded approved measurement paths.
- [x] Generalize persisted, fingerprint-bound, single-use approval to an executable backend adapter.
- [x] Add the SQLite evidence ledger and persistent experiment DAG.
- [x] Add objective, regression-guardrail, and compute-budget evaluation.
- [x] Add reversible local change handling: isolate, measure, retain or discard.
- [x] Add a deterministic threshold-calibration adapter and hidden-failure demo.
- [x] Add a declared ML training adapter and an end-to-end measured fixture.
- [x] Add a smaller backend benchmark adapter to prove core generality.
- [ ] Prototype AI-agent evaluation if core milestones are complete.
- [x] Live-validate a read-only NVIDIA Nemotron preview through Nebius Token Factory.
- [x] Build the browser workbench and polling-based run view.
- [x] Create an end-to-end demonstration on a small representative ML training repository.
- [ ] Add production deployment, stronger observability, and an external execution sandbox.

## Development principles

- Build incrementally and keep module boundaries explicit.
- Prefer a small working implementation over premature complexity.
- Treat external repositories and model output as untrusted input.
- Preserve tool outputs and provenance.
- Never claim an experiment was run without recorded execution evidence.
- Keep secrets out of source control.
- Update this README and `docs/PROJECT_CONTEXT.md` as architecture decisions change.
