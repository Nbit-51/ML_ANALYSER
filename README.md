# ML Analyser

An evidence-driven repository benchmarking workbench, with ML as its flagship use case. Define success, review a hypothesis, approve an experiment, and compare measured baseline/candidate results.

**Nemotron reasons. Adapters measure. Deterministic rules decide.**

Built with FastAPI, SQLite and lightweight JavaScript/SVG. Includes an offline mock provider.

## Run locally

Use Python 3.11+ and Node.js for frontend tests.

```sh
python -m venv .venv
```

Activate with `.venv\Scripts\Activate.ps1` on Windows or `source .venv/bin/activate` on Linux, then run:

```sh
python -m pip install -e ".[dev]"
python -m uvicorn ml_analyser.main:app --app-dir backend --reload
```

Open [the workbench](http://127.0.0.1:8000/app) or [API docs](http://127.0.0.1:8000/docs). The mock provider works without an API key.

To enable live reasoning, copy [.env.example](.env.example) to `.env` **only if `.env` does not already exist**. Set `ML_ANALYSER_MODEL_PROVIDER=nebius`, `NEBIUS_API_KEY` and `NEBIUS_MODEL`. Keep credentials local; `.env` is ignored. Live reasoning sends selected repository excerpts to Nebius.

## Try an experiment

1. Select the ML or HTTP demo, or preview a repository under `workspaces/`.
2. Set an objective and guardrails. Inspect the evidence and hypothesis.
3. Prepare the plan, review the exact change, and explicitly approve execution.
4. Inspect comparison charts, sample distributions, reliability, guardrails and experiment lineage.
5. Open the persisted report and evidence. Accepted candidates stay in isolated copies; the original repository stays unchanged.

## Supported benchmarks

| Adapter | What it runs | Requirement |
| --- | --- | --- |
| ML training | Classification or declared custom metrics, including regression | `ml_experiment.json`; trusted local Python |
| HTTP backend | Warm-ups, repeated batches, latency percentiles, throughput and response integrity | `backend_benchmark.json`; trusted local Python |
| Generic process | CLI, test-suite, build and microbenchmark harnesses | `repo_benchmark.json`; Linux + bubblewrap |

Run the API inside Linux/WSL for generic execution. On Ubuntu, install the sandbox with `sudo apt-get install bubblewrap`; namespaces must be enabled. Windows supports generic preview, without automatic WSL dispatch. Start with the [CLI fixture](workspaces/cli-benchmark-demo) and [manifest guide](docs/GENERIC_BENCHMARKS.md).

Repository previews detect languages, build/test systems and capabilities without executing code. Detection alone does not establish execution support. Custom metrics, raw samples, evidence references and reports use the same normalized API across adapters.

## Verify

```sh
python -m ruff check .
python -m ruff format --check backend
python -m mypy backend/ml_analyser
python -m pytest --cov=ml_analyser --cov-report=term-missing --cov-fail-under=90
node --test frontend/metrics.test.js frontend/analytics.test.js
```

Latest local validation: **107 Linux tests passed, 92.88% coverage; 10 frontend tests passed.** See [commands, results and file inventory](docs/IMPLEMENTATION_VALIDATION.md). CI also checks JavaScript syntax.

## Boundaries

Execution requires fingerprint-bound, single-use approval. Generic execution denies external network access and enforces bounded commands, outputs and per-process resources. Legacy ML/HTTP runners are for trusted local code. Keep the unauthenticated API on localhost.

This is a hackathon prototype: HTTP is sequential, ML training is not repeated, aggregate CPU/GPU/cost accounting is unavailable, and reliability rules do not establish statistical significance. Production workers, recovery and broader native ecosystem integrations remain future work.

Read [Architecture](docs/ARCHITECTURE.md), [Project context](docs/PROJECT_CONTEXT.md) and [Deployment/security](docs/DEPLOYMENT_AND_SECURITY.md) for details.
