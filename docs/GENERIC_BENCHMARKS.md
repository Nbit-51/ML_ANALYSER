# Declared repository benchmarks

The `generic_process` adapter executes explicitly configured CLI, test-suite, build, and microbenchmark harnesses. A detected language or build file alone never authorizes a command. Repository code is not executed by preview or preparation.

## Requirements and boundaries

Execution requires Linux, `/usr/bin/python3`, bubblewrap, and enabled unprivileged user/network/PID namespaces. Windows supports preview and the existing trusted ML/HTTP demonstrations; the generic adapter has no unsandboxed Windows fallback. Running the API inside Linux/WSL enables the Linux adapter. Installing bubblewrap alone does not guarantee that a host's namespace policy permits execution; a denied launch produces failed evidence, never an accepted measurement.

The sandbox exposes `/usr`, system binary/library directories, a fresh `/proc` and `/dev`, the repository copy read-only at `/work`, and exact declared output files as writable mounts. It does not mount the host home directory or inherit credentials. `--unshare-all` denies external network access. There is no shell command endpoint, package installation, implicit dependency download, or writable host repository mount. The current runtime allowlist is defined in `adapters/process.py`; ecosystem compatibility still depends on the installed runtime and a working declared harness.

Memory, CPU, file-size, descriptor and process limits are applied inside the namespace; wall-time and captured-output limits are enforced by the parent. Memory and CPU limits are per process, not aggregate cgroup accounting. Output mounts must be new files, not directories or existing inputs. Build systems that require arbitrary directory trees, writable caches, unavailable runtimes, or external downloads need a future adapter. This is a local prototype, not a multi-tenant hosting security guarantee.

## Manifest

Place `repo_benchmark.json` in the repository root. See the complete generated [JSON schema](repo_benchmark.schema.json) and the executable [CLI fixture](../workspaces/cli-benchmark-demo/repo_benchmark.json).

```json
{
  "adapter": "generic_process",
  "profile": "cli",
  "working_directory": ".",
  "command": ["/usr/bin/python3", "-I", "harness.py"],
  "config_file": "config.json",
  "candidate_overrides": {"repeats": 10},
  "metric_definitions": [
    {"name": "work_units", "unit": "operations", "direction": "minimize"},
    {"name": "process_duration_ms", "unit": "ms", "direction": "minimize"}
  ],
  "warmup_count": 1,
  "repetitions": 5,
  "allowed_output_paths": [],
  "environment": {},
  "network": "denied",
  "limits": {"timeout_seconds": 10, "cpu_seconds": 10, "memory_mb": 512,
             "output_bytes": 65536, "processes": 16}
}
```

Optional `build_command` and `test_command` are argv arrays and run before the benchmark command in every round. `metrics_file`, when set, must be in `allowed_output_paths` and is relative to the repository root. Commands run in `working_directory`; output paths always use repository-root coordinates. Every variant uses the same commands and workload. The only candidate operation is changing existing keys in the declared JSON configuration.

The benchmark emits one JSON object on stdout, or into the declared metric file:

```json
{"metrics": [{"name": "work_units", "value": 10, "unit": "operations"}],
 "correctness": "checksum-of-the-workload-result"}
```

All declared metrics must be emitted exactly once, with exact units and finite numeric values. Unknown fields, duplicate JSON keys, duplicate metrics, booleans, NaN and Infinity are rejected. If declared, `process_duration_ms` is emitted by the adapter and must not be supplied by the harness. It covers build, test and benchmark invocations including sandbox launch overhead. Other metrics, including workload-specific timing, come from the declared harness. Correctness is a harness assertion: the engine compares signatures but does not prove the harness itself is valid.

## Protocol and decisions

Preparation returns an immutable plan and pending approval. Approval binds the manifest, contract, hypothesis, source fingerprint and procedure. Execution rejects changed plans or source files, consumes approval once, copies both variants, verifies the copies, and applies the declared change only in the candidate copy.

Each pair alternates baseline/candidate order. Warm-ups are recorded separately and excluded from metric summaries. Every measured round has a persisted evidence record, including failures. Successful raw samples remain available; scalar means feed the evaluator. The default reliability rules require at least three samples, compatible environment fingerprints and units, no failed samples, and coefficient of variation at most 0.30 for required metrics. Unreliable required comparisons are inconclusive. A correctness mismatch rejects the candidate. No statistical significance test is claimed.

Declared output artifacts are captured within a bounded total byte limit, with SHA-256, base64 content and evidence references. Their persisted snapshots remain inspectable when a rejected candidate workspace is discarded. Reports are read from append-only evidence rather than regenerated from model memory.

The fixture's `work_units` objective counts actual repeated computations; it is not presented as a timing measurement. `elapsed_ms` and `process_duration_ms` are measured timings but can vary with host load. A repeated-measurement protocol reduces noise; it does not prove broad performance improvements.

## API

1. `POST /api/v1/runs/prepare` with `adapter`, `project_path`, and `success_contract`.
2. Review the returned `plan`, commands, limits and configuration changes.
3. `POST /api/v1/runs/approvals/{id}` with `{"approved": true}`.
4. `POST /api/v1/runs/execute` or `/start` with `adapter`, `approval_id`, and the unchanged `plan`.
5. Read `/api/v1/runs/live/{run_id}` for background progress and `/api/v1/runs/{run_id}/report` for the immutable normalized report.

ML training and HTTP benchmarks use the same registered API; their old endpoints remain available. The old endpoints retain their legacy response schemas. Normalized reports are produced by the generic API.
