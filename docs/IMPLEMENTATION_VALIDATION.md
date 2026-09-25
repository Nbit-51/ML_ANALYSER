# Implementation and validation record

Validated locally on 2026-09-25. These results describe the working tree, not a remote GitHub Actions run. Tests use deterministic mock reasoning; no live Nebius inference was claimed or required.

## Implemented architecture

The existing FastAPI, SQLite, approval binding, isolated candidate copies, append-only evidence and deterministic evaluator remain in place. A typed adapter registry now dispatches the generic prepare/execute/start API to ML training, HTTP and declared generic process implementations. Normalized reports are persisted as evidence. Custom finite ML metrics, repeated process/HTTP observations, transparent reliability rules and provenance flow into an adapter-neutral JavaScript/SVG workbench.

Generic CLI, test-suite, build and microbenchmark profiles share an explicitly declared harness protocol. Real execution requires Linux bubblewrap containment. Static capability discovery covers languages, build/test configuration, entrypoints, ML/API indicators, CI, datasets, models and result artifacts, with detected/declared/inferred/measured provenance and evidence references.

The workbench includes metric comparison charts, deltas, shared-bin distributions, objective/guardrail status, reliability details, source-byte composition, execution readiness, selectable experiment lineage and expandable evidence/artifacts.

## Commands and actual results

Commands ran from the repository root. Windows used the existing `.venv/Scripts/python.exe` because the system Python did not contain the lint/type-check tooling.

| Command | Result |
| --- | --- |
| `.venv/Scripts/python.exe -m ruff check .` | Passed |
| `.venv/Scripts/python.exe -m ruff format --check backend` | Passed; 65 files formatted |
| `.venv/Scripts/python.exe -m mypy backend/ml_analyser` | Passed; 47 source files |
| `.venv/Scripts/python.exe -m pytest --cov=ml_analyser --cov-report=term-missing --cov-fail-under=90 -q` | 91 passed, 16 explicitly Linux-only tests skipped; 90.54% coverage; two dependency deprecation warnings |
| Linux Python: `-m pytest --cov=ml_analyser --cov-report=term-missing --cov-fail-under=90 -q` | 107 passed; 92.88% coverage; one dependency deprecation warning |
| `node --check frontend/app.js` | Passed |
| `node --check frontend/analysis.js` | Passed |
| `node --check frontend/metrics.js` | Passed |
| `node --check frontend/analytics.js` | Passed |
| `node --check frontend/workbench.js` | Passed |
| `node --test frontend/metrics.test.js frontend/analytics.test.js` | 10 passed |
| `git diff --check` | Passed; Git reported line-ending normalization warnings |

Linux validation ran under WSL Ubuntu 24.04 with a dedicated test virtual environment and coverage/cache files outside the checkout. The command below preserves the executed arguments, replacing local machine paths with placeholders:

```text
<linux-venv>/bin/python -m pytest --cov=ml_analyser --cov-report=term-missing --cov-fail-under=90 -q -o cache_dir=<external-cache-directory>
```

`COVERAGE_FILE` pointed to an external coverage-data file.

Ubuntu test tooling and bubblewrap were installed with permission. Fixtures and test execution do not download datasets, models or project dependencies. CI installs bubblewrap and runs the same coverage threshold plus all frontend tests.

Browser checks used the local mock-provider API: ML and HTTP preparation, explicit approval and execution completed with accepted decisions. Comparison/distribution charts, guardrail and reliability panels, lineage, evidence and reports were inspected. The HTTP run recorded 60 successful requests per variant and three measured batches. Browser error logs were empty. A narrow-screen layout problem found during inspection was corrected by stacking metric panels below 480px.

## Behavioral tests and fixtures

- Existing classification and HTTP workflows remain covered. The new regression fixture demonstrates a custom RMSE metric and minimization.
- Generic CLI and build/test fixtures use offline Python standard-library harnesses with declared configuration improvements. Instrumented work count and elapsed timings have separate meanings.
- Linux integration tests run all four generic profiles through actual sandbox execution and accepted, rejected and inconclusive outcomes. They assert evidence, decision reasons and unchanged original sources.
- Protocol/security tests cover duplicate/missing metrics, wrong units, booleans and nonfinite numbers, malformed output, variance/failures/environment mismatch, source/plan tampering, approval replay, path/symlink escapes, network/write denial, timeouts, output bounds and retained artifact snapshots after candidate discard.
- Frontend tests cover custom/unknown metrics and units, contract direction, deltas, guardrail states, distributions, reliability data and branching experiment graphs.
- Fake runners in portable protocol unit tests are explicit; they are distinct from real Linux execution tests.

## Created files

Backend:

- `backend/ml_analyser/adapters/process.py`
- `backend/ml_analyser/adapters/registry.py`
- `backend/ml_analyser/agent/analytics.py`
- `backend/ml_analyser/agent/measurements.py`
- `backend/ml_analyser/agent/process_benchmark.py`
- `backend/ml_analyser/api/routes/benchmarks.py`
- `backend/ml_analyser/execution/sandbox.py`
- `backend/ml_analyser/execution/sandbox_limits.py`
- `backend/ml_analyser/tools/capabilities.py`
- `backend/tests/test_generalized.py`
- `backend/tests/test_sandbox_execution.py`

Frontend and documentation:

- `frontend/analytics.js`
- `frontend/analytics.test.js`
- `frontend/workbench.js`
- `docs/GENERIC_BENCHMARKS.md`
- `docs/repo_benchmark.schema.json`
- `docs/IMPLEMENTATION_VALIDATION.md`

Fixtures:

- `workspaces/cli-benchmark-demo/`: `README.md`, `config.json`, `harness.py`, `prepare_request.json`, `repo_benchmark.json`.
- `workspaces/build-test-demo/`: `README.md`, `build.py`, `config.json`, `harness.py`, `prepare_request.json`, `repo_benchmark.json`, `tests.py`.
- `workspaces/ml-regression-demo/`: `config.json`, `ml_experiment.json`, `prepare_request.json`, `train.py`.

## Modified files

- `.github/workflows/ci.yml`, `.gitignore`, `README.md`.
- `backend/ml_analyser/adapters/backend_http.py`, `backend/ml_analyser/adapters/ml_training.py`.
- `backend/ml_analyser/agent/backend_benchmark.py`, `backend/ml_analyser/agent/evaluator.py`, `backend/ml_analyser/agent/ml_training.py`, `backend/ml_analyser/agent/models.py`, `backend/ml_analyser/agent/orchestrator.py`, `backend/ml_analyser/agent/state_graph.py`.
- `backend/ml_analyser/api/router.py`, `backend/ml_analyser/api/routes/runs.py`, `backend/ml_analyser/tools/repository_context.py`.
- `frontend/analysis.js`, `frontend/app.js`, `frontend/index.html`, `frontend/metrics.js`, `frontend/metrics.test.js`, `frontend/styles.css`.
- `docs/ARCHITECTURE.md`, `docs/PROJECT_CONTEXT.md`, `docs/DEPLOYMENT_AND_SECURITY.md`.

## Remaining limits and intentionally deferred work

- Generic execution requires Linux plus working bubblewrap namespaces. Windows generic readiness is preview-only; automatic WSL dispatch is not implemented.
- Legacy ML/HTTP execution remains suitable for trusted local demonstrations, not hostile repositories.
- Resource enforcement is per process. Aggregate cgroups, measured CPU/GPU/cost accounting and production multi-tenant containment are deferred. Generic execution refuses aggregate CPU/GPU budget contracts it cannot measure.
- Generic writable paths are exact new files; arbitrary build-cache trees and dependency downloads are unsupported. Native C/C++, Node, Go, Rust and Java integrations have not been demonstrated merely by detecting their build files.
- HTTP uses repeated sequential batches; concurrency and baseline/candidate HTTP interleaving are deferred. ML training remains a single run per variant.
- Reliability uses deterministic sample/variance/failure/environment rules. Statistical significance is not claimed. Harness correctness signatures do not establish the validity of the harness itself.
- Capability/graph relationships are conservative static heuristics rather than full program analysis.
- Durable workers, restart recovery, cancellation, authentication for shared deployment and automatic source promotion remain future work.
