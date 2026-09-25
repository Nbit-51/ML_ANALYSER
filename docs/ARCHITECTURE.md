# Architecture

## Implemented system

ML Analyser is a local evidence-driven repository experimentation engine with ML as its flagship use case. FastAPI exposes typed contracts and controlled experiments; SQLite stores approvals, append-only evidence, run events and experiment lineage; the browser uses lightweight JavaScript and SVG. Existing classification, threshold and HTTP demonstrations remain available.

```text
Repository -> read-only inventory -> capability facts and project graph
           -> bounded evidence selection -> mock / Nemotron hypotheses
Success contract + declared adapter profile -> preparation -> exact approval
           -> copied baseline/candidate -> adapter measurement protocol
           -> normalized observations -> deterministic evaluator
           -> immutable evidence + experiment DAG -> report + visual workbench
```

## Domain and measurements

`agent/models.py` defines objectives, constraints, multidimensional budgets, strict manifests, hypotheses, experiments, approvals, measurements and decisions. Unknown fields and nonfinite numeric values are rejected. Measurement retains a scalar for contract evaluation plus raw samples, optional batch-level reliability samples, descriptive statistics, warm-ups, failures, timestamps, environment fingerprint and evidence IDs.

`agent/measurements.py` computes mean, median, min/max, interpolated percentiles, sample standard deviation and coefficient of variation. `agent/evaluator.py` decides accepted/rejected/inconclusive without model discretion. Missing required metrics, incompatible units/environments, fewer than three repeated samples, failures or CV above 0.30 undermine required comparisons. Scalar-only ML results explicitly remain reliability-not-assessed. Custom metric direction comes from the contract or explicit metadata.

## Adapter registry

`adapters/registry.py` binds adapter identity, manifest name, profile types, requirements, plan schema, validator, pipeline factory and observation normalizer. The API and background dispatcher use registration lookup, not growing adapter-name conditionals. Legacy pipelines retain domain-specific execution details and endpoints for compatibility.

- `ml_training`: runs a declared Python script with a JSON config and structured metrics file. Default classification definitions preserve old manifests; explicit definitions support custom regression/inference metrics and known bounds.
- `backend_http`: starts a trusted local Python server, performs warm-ups and repeated sequential request batches, retains successful-request latency samples, separates errors, computes P50/P95/P99 and compares response content. Reliability uses per-batch summaries rather than pretending requests are independent experiment repetitions.
- `generic_process`: runs an explicit CLI/test/build/microbenchmark harness manifest under Linux bubblewrap. It alternates baseline/candidate ordering, persists every round (including warm-ups and failures), compares correctness signatures and evaluates means. Optional `process_duration_ms` is tool-measured across build/test/benchmark commands; other declared metrics originate in the harness.

Registration does not imply every ecosystem is executable. Missing manifests require configuration; missing sandbox support means preview only. An installed runtime plus compatible declared harness is required. The general runner never installs dependencies or executes a command inferred from a README.

## Repository understanding

`tools/repository.py` inventories bounded file metadata without importing code. Composition uses bytes of inventoried source files, not file counts presented as LOC. `tools/capabilities.py` returns conservative filename/category evidence for languages, package/build systems, test suites, benchmark files, CI, containers, likely entrypoints, ML/web indicators, data, models, results and configuration.

Capability provenance distinguishes detected facts, declared profile configuration, inferred relationships and measured outputs. Static indicators do not establish runtime compatibility. Project graphs preserve file/category structure and add languages and capability relationships with evidence and confidence. Completed experiment graphs connect repository, experiments, dependencies and measurements. No arbitrary semantic call graph is claimed.

The context collector deterministically ranks requested objective/guardrail tokens, benchmark/config/test/entrypoint names, README lines and result filenames. It selects bounded excerpts (six source/config/test excerpts, two prior result records, one README; 1,600 characters per excerpt). Secret-like filenames, environment files and lockfiles are excluded. Responses expose model-context flags and exact excerpts; prior records are not new measurements. Nebius structured output and the preview orchestrator reject nonexistent evidence IDs. Source grounding is evidence validation, not proof every proposed explanation is correct.

## Approval, isolation and sandbox

`ApprovalService` persists a canonical plan fingerprint. SQLite uses conditional updates for single-use authorization. Changing a contract, manifest, hypothesis, command or source fingerprint invalidates scope. Generic execution also verifies copied inventories before running code.

`IsolatedWorkspaceManager` rejects symlink-containing sources, creates separate baseline/candidate copies, and constrains cleanup to the execution root. Accepted candidates remain isolated; other candidates are discarded. Promotion to the source repository is not implemented.

The generic sandbox uses a fresh network/user/PID namespace, read-only runtime directories and `/work`, exact writable artifact files, an explicit environment allowlist, bounded stdout/stderr and timeouts. Trusted resource-limit setup occurs inside the namespace before executing the declared argv. It denies host-home access, external network and undeclared writes. Memory/CPU/process/file limits are per process; aggregate cgroup enforcement is future work. See [the benchmark guide](GENERIC_BENCHMARKS.md) for the executable surface and limitations.

Legacy ML/HTTP runners remain trusted local demonstrations. Workspace copies are not an OS security boundary for hostile scripts; these adapters are labeled accordingly. No safety claim about the generic sandbox is retroactively applied to them.

## Persistence, API and reports

SQLite tables store append-only evidence and experiment DAG nodes, exact approvals, live-run snapshots and stage events. New normalized results are serialized into an immutable evidence record and read back for delivery. Reports contain repository identity, contract, hypothesis, exact change, source fingerprint, declared command/configuration, measurement methodology, comparisons, reliability, guardrails, resource usage, evidence IDs, disposition and limitations. No report depends on model memory.

| Endpoint | Role |
| --- | --- |
| `POST /api/v1/runs/preview` | Read-only repository evidence and hypotheses |
| `POST /api/v1/runs/prepare` | Registered adapter plan and pending approval |
| `POST /api/v1/runs/approvals/{id}` | Approve/reject exact scope |
| `POST /api/v1/runs/execute` | Synchronous normalized measured result |
| `POST /api/v1/runs/start` | Queue local background execution |
| `GET /api/v1/runs/live/{id}` | Persisted progress/result |
| `GET /api/v1/runs/{id}/report` | Immutable normalized report |

Legacy `/ml-training/*`, `/backend-benchmark/*` and `/ml-threshold-demo` endpoints remain available with their original response shapes. Generic endpoints return typed union plans and common result schemas. Background execution uses local FastAPI tasks, not a durable distributed worker; restart recovery and cancellation remain future work.

## Frontend

`analytics.js` contains pure, adapter-neutral transformations tested under Node. `workbench.js` renders SVG metric comparisons, shared-bin sample histograms, a rule-by-rule guardrail table, reliability diagnostics, byte composition, a selectable experiment DAG and evidence disclosures. Units and directions come from backend data. Unknown units and custom metrics remain renderable. The frontend contains no adapter-specific list of result metrics.

## Validation and scope

CI enforces Ruff lint/format, strict mypy, backend coverage >=90%, JavaScript syntax checks and frontend transformation tests. Linux integration tests execute actual CLI, test, build and microbenchmark profiles and validate network/write denial, timeout and output bounds. Other tests cover custom ML metrics, HTTP results, approval replay/tampering, source changes, malformed/duplicate/nonfinite output, reliability and source isolation.

This remains a local hackathon prototype. Native C/C++/Node/Go/Rust/Java-specific benchmark integrations, agent evaluation, frontend browser benchmarks, HTTP concurrency, statistical testing, aggregate accounting, production workers and automatic source promotion are not implemented.
