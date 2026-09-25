# Project context

## Product intent

Preserve the evidence-driven verification architecture: a machine-readable success contract, falsifiable hypotheses, explicit approval, isolated experiments, deterministic measurement evaluation, an append-only ledger and persistent lineage. ML remains the flagship domain; the engine also supports declared non-ML process benchmarks.

AI-generated claims are hypotheses until measured. Preview, prior files, and provider estimates must never be displayed as executed results. Nemotron through Nebius is the real optional reasoning provider; the default mock provider is deterministic and offline. Neither decides numeric acceptance or supplies measurements.

## Current implementation

- FastAPI, Pydantic, SQLite and a lightweight JavaScript/SVG workbench; no framework migration or distributed infrastructure.
- Generic prepare/execute/start paths dispatch through `AdapterRegistry`; existing ML/HTTP endpoints remain compatible.
- Capability facts and deterministic graphs carry provenance/evidence; language composition explicitly means source-file bytes.
- ML manifests can declare arbitrary finite metrics and units, bounds and direction. Classification defaults remain backward compatible. A regression fixture demonstrates minimization.
- General process manifests define argv, working directory, optional build/test commands, output protocol, metrics, repetitions, warm-ups, resource limits, environment/output allowlists and JSON candidate overrides.
- Linux bubblewrap is required for generic execution. Windows API processes expose preview/configuration readiness; there is no unsandboxed fallback. WSL can run the API and tests as a Linux host.
- Generic samples alternate execution order. HTTP uses warm-ups and repeated sequential batches; successful-request samples and failure counts remain separate.
- Reliability rules are deterministic: required repeated comparisons need compatible units/environments, >=3 samples, zero failed samples and CV <=0.30. Raw samples remain visible. No statistical significance is claimed.
- Generic API results and reports are serialized into immutable evidence and read back. Evidence links and experiment parent relationships are inspectable.
- The workbench renders arbitrary metrics, deltas, sample distributions, guardrails, reliability, capabilities, lineage and persisted reports.

## Fixtures and testing

Classification training, custom regression, saved-threshold predictions, HTTP, generic CLI and build/test fixtures are committed. All are small and offline. Linux integration tests run CLI, test-suite, build and microbenchmark profiles through preparation, approval and real sandbox execution; they assert accepted, rejected and inconclusive decisions and unchanged source files. Windows skips Linux-only integration tests explicitly.

The CLI acceptance objective is instrumented redundant work count, not fabricated latency. The harness separately measures elapsed time and the adapter can measure full command duration. Test doubles are used in protocol unit tests and are separate from real Linux execution tests.

CI retains the 90% coverage requirement and includes the new frontend transformation tests. Exact local validation commands/results are recorded in `docs/IMPLEMENTATION_VALIDATION.md` after final checks.

## Deliberate limits

- Local ML/HTTP runners are trusted demos, not hardened execution of hostile scripts.
- Generic sandbox resource limits are per process; aggregate accounting is not available. It rejects CPU/GPU aggregate budget contracts it cannot measure.
- Generic writable paths are exact new files. Build ecosystems needing arbitrary writable directory trees/caches or downloads require additional adapter work.
- Capabilities are conservative static heuristics. Recognized build systems do not establish native ecosystem execution support.
- Repeated ML training, HTTP concurrency/interleaving, statistical significance testing, cancellation/recovery, production scheduling and source promotion are future work.
- Correctness signatures come from the harness and cannot establish the harness's correctness by themselves.
- CPU/GPU/cost usage is not instrumented. Resource fields inherited from the prototype must be read with the report's accounting limitations.

## Configuration

`ML_ANALYSER_WORKSPACE_ROOT`, `ML_ANALYSER_EXECUTION_ROOT`, and `ML_ANALYSER_STATE_DATABASE` control local paths. Repository paths remain constrained to the configured workspace. `ML_ANALYSER_MODEL_PROVIDER=mock` is offline; `nebius` requires `NEBIUS_API_KEY` and `NEBIUS_MODEL`. Never print or commit credentials. Live preview sends bounded selected excerpts to Nebius; ordinary tests force mock reasoning.
