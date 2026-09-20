# Architecture

## Overview

ML Analyser is designed as a closed-loop, evidence-driven optimization system. It accepts a technical project and a machine-readable success contract, forms falsifiable hypotheses, runs controlled experiments, and keeps a change only when measured evidence satisfies both the objective and every guardrail.

The architecture separates HTTP transport, domain-neutral orchestration, project understanding, domain adapters, inference providers, guarded execution, evaluation, persistence, and presentation. ML is the flagship adapter; the core vocabulary is goal, metric, constraint, hypothesis, experiment, observation, and decision.

The first vertical slice now implements strict domain contracts, lifecycle transitions, bounded inventory, a deterministic project state graph, a local mock provider, dry-run experiment compilation, deterministic decision rules, SQLite evidence/DAG persistence, and a narrow ML threshold-calibration demo. General command execution, reversible patch application, broad domain adapters, external inference, and the frontend remain planned and must not be presented as implemented.

## System context

```text
User + success contract
          |
          v
Web frontend (planned) -> FastAPI service
                              |
                              v
                 Closed-loop orchestrator
                    |         |         |
                    v         v         v
              Project     Hypothesis  Experiment DAG /
              state graph + compiler  evidence ledger
                    |         |         |
                    v         v         v
              Domain adapter and measurement contract
                    |                   ^
                    v                   |
            Guarded experiment runner -> evaluator/decision policy
                    |
              isolated workspace / compute

Nemotron through Nebius -> structured reasoning requests to the orchestrator
```

## Product boundary

The product is not a universal coding agent. Coding agents primarily produce code changes; this system optimizes a measurable outcome and verifies whether a provisional change helped.

Domain adapters prevent “works on everything” from becoming an unsupported claim:

| Adapter | Hackathon scope | Measurements |
| --- | --- | --- |
| ML | Fully functional flagship | F1/AP/loss, latency, VRAM, model size, training evidence |
| General software benchmark | Smaller functional proof | P50/P95, throughput, tests, memory, CPU, errors |
| AI-agent evaluation | Prototype/stretch | Task success, evaluator score, latency, token cost |

An adapter defines discovery rules, allowed interventions, measurement tools, comparison semantics, and compatibility checks. The core engine remains unaware of whether a metric is F1 or P95 latency.

## Component boundaries

### API layer

Responsibilities:

- validate external requests and success contracts;
- create and query optimization runs;
- expose progress, hypotheses, evidence, experiment lineage, budgets, and reports;
- map domain errors to stable HTTP responses.

The API layer must not contain decision logic or issue arbitrary shell commands. The current implementation exposes only a service root and versioned health check.

### Application services (planned)

Responsibilities:

- coordinate repository intake and run lifecycle operations;
- enforce legal run-state transitions;
- invoke the agent runtime, adapter, and persistence ports;
- provide cancellation, approvals, and status updates.

### Success contract (planned)

Each run begins with a validated contract containing:

- primary objective metric, direction, and optional target;
- hard constraints and permitted regression tolerances;
- budget dimensions such as money, GPU/CPU minutes, tokens, experiment count, and wall-clock time;
- adapter identity and measurement configuration.

Missing measurements cannot pass a constraint. Estimates and observations must remain separate fields.

### Agent runtime (planned)

The orchestrator will be a state machine, not a free-form chat loop:

```text
CREATED -> INGESTING -> DIAGNOSING -> HYPOTHESIZING -> DESIGNING
        -> SELECTING -> AWAITING_APPROVAL -> EXECUTING -> MEASURING
        -> DECIDING -> REVISING or REPORTING -> COMPLETED

Any active state -> FAILED or CANCELLED
```

Some runs may skip execution when no safe or affordable experiment is available. That transition must be explicit and represented in the report.

Core responsibilities:

- build structured context from repository artifacts and previous runs;
- request typed diagnoses and falsifiable hypotheses;
- compile selected hypotheses into minimal reproducible experiments;
- rank candidates under information gain, expected improvement, risk, and remaining budget;
- validate proposed actions against policy;
- schedule approved actions through the guarded runner;
- convert outputs into evidence records;
- compare observations with a compatible baseline, objective, and every guardrail;
- keep or revert the provisional change and select the next experiment;
- generate a report from durable state.

### Model provider port (planned)

The runtime will depend on a small interface accepting structured messages and response schemas. Implementations are expected for:

- a deterministic local/mock provider for tests and offline development;
- NVIDIA Nemotron through Nebius Token Factory for the hackathon path.

For an expensive action, Nemotron may provide structured diagnostic, skeptic, experiment-planner, and judge perspectives. These are workflow responsibilities, not necessarily separately deployed agents. Deterministic application code retains final authority over schemas, budgets, policy, and pass/fail decisions.

Provider adapters own authentication, endpoint details, timeouts, retry classification, and relevant usage metadata. They must surface errors and never substitute fabricated output.

### Project state graph (planned)

The repository must not be flattened into one model prompt. A versioned state graph connects:

- source files, entry points, dependencies, and code revisions;
- datasets, schemas, splits, fingerprints, and preprocessing;
- configurations and hyperparameters;
- models, checkpoints, and runtime environments;
- metrics, logs, benchmarks, tests, and artifacts;
- hypotheses, observations, and experiment lineage.

Graph entities retain source references and freshness metadata. A project-state change determines whether an earlier experimental conclusion is still applicable.

### Hypothesis engine and experiment compiler (planned)

A hypothesis is a typed, falsifiable claim recording the suspected cause, supporting evidence, uncertainty, proposed intervention, target metric effect, protected guardrails, success threshold, and rejection rule.

The experiment compiler translates an approved hypothesis into a reproducibility bundle:

- parent/baseline experiment;
- isolated code patch or configuration delta;
- exact command and working directory;
- dataset/project snapshot and environment identity;
- expected measurements and comparison method;
- estimated duration, resource demand, and cost;
- artifact-capture and safe-revert instructions.

Compilation does not imply execution. Policy validation must approve the bundle before it reaches the runner.

### Experiment selector (planned)

The selector ranks valid candidate experiments using interpretable factors:

- expected information gain: how much the result distinguishes competing diagnoses;
- expected objective improvement and probability of success;
- execution and rollback risk;
- estimated cost across every budget dimension;
- remaining budget and dependency ordering.

A cheap diagnostic can outrank a more promising but expensive change when it eliminates more uncertainty per unit cost. Initial heuristics should remain auditable; more complex optimization is unnecessary until evaluation data justifies it.

### Tool registry and guarded runner (planned)

Tools have typed input/output schemas and declared capabilities. Early tools may include repository inventory, targeted search, dependency/config inspection, tests, linters, log and metric parsers, benchmarks, and narrowly scoped training/evaluation commands.

The runner validates each request, executes it in an isolated project workspace, enforces time and resource limits, captures stdout/stderr and exit status, and records generated artifacts. A candidate patch is provisional: a rejected, invalid, failed, or inconclusive experiment does not modify the accepted project state.

### Evaluator and decision policy (planned)

The evaluator checks measurement compatibility before comparison. A decision can be:

- **accepted:** the configured objective rule passes and every hard guardrail passes;
- **rejected:** the objective or a guardrail fails with valid measurements;
- **inconclusive:** required evidence is missing, invalid, or incomparable.

Passing tests is a guardrail, not proof that the objective improved. Decision records include before/after values, deltas, tolerances, constraint status, and links to raw evidence.

### Evidence ledger and experiment DAG (planned)

Every material conclusion references evidence. Experiments form a directed acyclic graph, not a linear chat transcript:

```text
Run
|-- state transitions
|-- success contract and budget ledger
|-- project state graph version
|-- findings[] -> evidence_refs[]
|-- hypotheses[]
|-- experiment DAG
|   `-- experiment node
|       |-- parent experiment and hypothesis
|       |-- code revision, patch, and configuration
|       |-- dataset/project version and environment/hardware
|       |-- command, policy decision, timestamps, and exit status
|       |-- estimated and actual time/cost/resources
|       |-- metrics, logs, and artifact references
|       `-- baseline comparison, guardrails, and decision
`-- report
```

Large outputs and binary artifacts live in artifact storage; persistence records contain hashes, metadata, and stable references. Rejected hypotheses remain searchable and are reconsidered only if relevant project state changes.

### Frontend (planned)

The frontend should optimize for a short, legible demonstration:

- define or load a success contract;
- observe the diagnose-to-decision stage and remaining budget;
- review hypotheses and approve guarded execution where required;
- compare baseline and candidate measurements with every constraint;
- inspect experiment lineage, rejected ideas, and why each change was kept or reverted;
- read the final evidence-backed report.

Visual complexity that does not reinforce trust, evidence, or progress should be avoided.

## End-to-end request flow

1. The API creates a run from a validated workspace and success contract.
2. The adapter inventories project artifacts and establishes a compatible baseline.
3. Analysis tools and previous runs populate the project state graph.
4. The provider produces structured diagnoses and falsifiable hypotheses.
5. The compiler creates candidate reproducibility bundles.
6. The selector ranks candidates by information/value, risk, and remaining budget.
7. Policy rejects unsafe or malformed operations and requests approval where required.
8. The runner applies the candidate in isolation, executes it, and persists raw outputs.
9. The adapter normalizes measurements; the evaluator checks the objective and guardrails.
10. The decision stage accepts, rejects, or marks the hypothesis inconclusive, then keeps or reverts the candidate.
11. The evidence ledger, project state graph, experiment DAG, and budget ledger are updated.
12. The result drives the next experiment or ends the loop and produces the report.

## Safety model

Repositories, their scripts, generated patches, and model output are untrusted. Before arbitrary execution is enabled, the system should:

- canonicalize and constrain paths to the assigned workspace;
- begin with read-only analysis;
- isolate every candidate change from accepted project state;
- allowlist executable tools and validate typed arguments;
- deny implicit network access unless a tool explicitly requires and receives it;
- prevent secrets from entering model context, logs, or reports;
- set wall-clock, CPU, GPU, memory, disk, spend, and output limits;
- record the command, directory, environment allowlist, and exit code;
- require approval for destructive, expensive, or externally visible operations;
- treat generated artifacts as untrusted until inspected;
- make rejection/revert idempotent and preserve its evidence.

## API conventions

- Product APIs are versioned below `/api/v1`.
- Health endpoints stay dependency-light.
- Request and response bodies use Pydantic models.
- Domain behavior belongs outside route functions.
- Errors will use stable machine-readable codes once domain endpoints are added.

Current endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Service identity and documentation link. |
| `GET` | `/api/v1/health` | Process health and version. |

## Observability (planned)

Use structured logs with run, stage, experiment, tool-call, adapter, and provider-request identifiers. Capture latency, token usage when available, tool duration, resource/cost estimates and observations, failure categories, decisions, and state transitions. Secret values and sensitive repository content must be redacted.

## Testing strategy

- **Unit tests:** contracts, state transitions, policies, selectors, parsers, comparisons, budgets, and adapters.
- **Contract tests:** model-provider, domain-adapter, and tool schemas.
- **API tests:** validation, lifecycle behavior, and error mapping.
- **Integration tests:** deterministic mock-provider runs over small fixture repositories.
- **Decision tests:** known baselines/candidates covering accept, reject, inconclusive, and revert behavior.
- **End-to-end tests:** deployed ML demo plus a smaller software benchmark path.

The current test suite covers the minimal HTTP surface. Agent behavior will be added only when its interfaces exist.

## Deployment direction

Packaging and deployment will be selected after the first vertical slice. A production deployment should separate the web/API process from resource-intensive experiment execution, use managed secrets, persist run state outside process memory, and support cancellation and recovery. Nebius infrastructure is the intended hackathon deployment target.
