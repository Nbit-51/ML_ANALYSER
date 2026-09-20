# ML Analyser

ML Analyser is an autonomous evidence-driven optimization agent being built for the **Nebius x NVIDIA Global AI Hackathon 2026**, in the **Best Apps & Agents** track. ML is the flagship adapter and primary demonstration, while the underlying engine is designed around domain-neutral goals, metrics, constraints, experiments, observations, and decisions.

> **Coding agents optimize code. ML Analyser optimizes measurable outcomes—and proves whether a change helped.**

It is designed to diagnose technical failures, turn explanations into falsifiable hypotheses, compile the smallest useful controlled experiments, execute them safely, and retain only changes supported by recorded evidence. The hackathon MVP goes deepest on ML experimentation.

> Status: project initialization. The repository currently contains documentation and a minimal FastAPI service. The agent runtime, model providers, tools, frontend, and experiment runner are planned work and are not represented as complete.

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

Nothing depends on claiming that a particular model is irreplaceable. Nemotron through Nebius powers reasoning; the execution, lineage, evaluation, and memory layers create the product value.

The same core loop can optimize different measurable systems through adapters:

| Adapter | Example objective | Example guardrails |
| --- | --- | --- |
| ML (flagship) | Maximize validation F1 | Recall, VRAM, latency, model size |
| Backend benchmark | Reduce P95 API latency | Tests, memory, error rate, throughput |
| AI-agent evaluation (prototype) | Improve task success | Token cost, latency, evaluator score |

The project will not claim to improve every codebase. The core engine owns verification and experimental lineage; each adapter must explicitly define what can be observed, changed, measured, and compared in its domain.

## Planned agent workflow

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

The planned system has six major components:

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

See [Architecture](docs/ARCHITECTURE.md) for component boundaries, run states, safety rules, and the intended data model. See [Project context](docs/PROJECT_CONTEXT.md) for constraints and current decisions.

## Technology stack

Current foundation:

- Python 3.11+
- FastAPI
- Pydantic Settings
- Uvicorn
- Pytest and HTTPX
- Ruff and mypy

Planned additions:

- a minimal recruiter-friendly web frontend (framework to be selected when frontend work begins);
- durable run/evidence persistence;
- isolated tool execution for repository analysis and experiments;
- structured tracing and streaming progress updates.

## Planned Nebius and NVIDIA integration

The primary reasoning provider will target an **NVIDIA Nemotron open-source model served through Nebius Token Factory**. The exact model identifier and deployment settings will be configured only after API access is available and validated; they are intentionally not hard-coded today. Nemotron will support structured diagnosis, skeptical review, experiment planning, and decision review, while deterministic code enforces schemas, budgets, policies, and acceptance rules.

The provider boundary will keep orchestration independent from any one inference API. A local/mock provider will be implemented first so the full state machine can be tested deterministically. The Nebius provider will then map structured agent requests to Token Factory, use environment-based credentials, preserve relevant request/response metadata, and expose provider failures without inventing completions.

No API credentials belong in this repository. `.env.example` contains variable names only; local values should be stored in an ignored `.env` file or a deployment secret manager.

## Repository layout

```text
.
|-- backend/
|   |-- ml_analyser/
|   |   |-- agent/          # Placeholder for a later milestone
|   |   |-- api/routes/     # HTTP route modules
|   |   |-- core/           # Configuration and cross-cutting concerns
|   |   `-- main.py         # FastAPI application factory
|   `-- tests/              # Backend tests
|-- docs/
|   |-- ARCHITECTURE.md
|   `-- PROJECT_CONTEXT.md
|-- frontend/               # Frontend placeholder; not implemented yet
|-- artifacts/              # Generated outputs (ignored except placeholder)
|-- workspaces/             # Local project workspaces (ignored except placeholder)
|-- .github/workflows/ci.yml
|-- .env.example
|-- AGENTS.md
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

No external credentials are needed for the current health-check service.

### Run the API

```bash
uvicorn ml_analyser.main:app --app-dir backend --reload
```

Then open:

- API root: <http://127.0.0.1:8000/>
- health check: <http://127.0.0.1:8000/api/v1/health>
- OpenAPI UI: <http://127.0.0.1:8000/docs>

### Quality checks

```bash
pytest
ruff check .
mypy backend/ml_analyser
```

## Roadmap

- [x] Initialize repository structure and engineering conventions.
- [x] Document project context and target architecture.
- [x] Add a minimal, tested FastAPI service.
- [x] Add CI for tests, linting, and type checking.
- [ ] Define typed agent, model-provider, tool, evidence, and run-state interfaces.
- [ ] Add a deterministic local/mock model provider.
- [ ] Implement repository inventory and the project state graph.
- [ ] Implement falsifiable hypothesis and experiment-compiler schemas.
- [ ] Implement explicit approval, execution, measurement, and decision stages.
- [ ] Add the evidence ledger and persistent experiment DAG.
- [ ] Add objective, regression-guardrail, and compute-budget evaluation.
- [ ] Add reversible change handling: isolate, measure, keep or revert.
- [ ] Complete the ML adapter and an end-to-end hidden-failure demo.
- [ ] Add a smaller backend benchmark adapter to prove core generality.
- [ ] Prototype AI-agent evaluation if core milestones are complete.
- [ ] Integrate NVIDIA Nemotron through Nebius Token Factory.
- [ ] Build the frontend and real-time run view.
- [ ] Create an end-to-end demonstration on a representative ML repository.
- [ ] Add deployment guidance, observability, security review, and Devpost materials.

## Development principles

- Build incrementally and keep module boundaries explicit.
- Prefer a small working implementation over premature complexity.
- Treat external repositories and model output as untrusted input.
- Preserve tool outputs and provenance.
- Never claim an experiment was run without recorded execution evidence.
- Keep secrets out of source control.
- Update this README and `docs/PROJECT_CONTEXT.md` as architecture decisions change.
