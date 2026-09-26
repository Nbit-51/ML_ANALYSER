# Deployment and security notes

## Current deployment profile

The application is suitable for a controlled local demonstration with the committed fixtures. Install with `pip install -e ".[dev]"`, keep `ML_ANALYSER_MODEL_PROVIDER=mock` until credentials are available, and start with `uvicorn ml_analyser.main:app --app-dir backend --host 127.0.0.1 --port 8000`. Open `/app` for the workbench. SQLite state and isolated run copies are stored under ignored `artifacts/` by default.

The FastAPI `BackgroundTasks` implementation is deliberately local. A process restart can interrupt an experiment and leave its last snapshot nonterminal. It is not a durable queue and should not be used to promise reliable long-running production jobs. Before shared deployment, move execution to a supervised worker with explicit leases, cancellation, restart reconciliation, per-run quotas, and externally persisted artifacts.

## Trust boundary

Repository inventory and preview are read-only; they do not import target code. The executable ML and backend adapters run a manifest-declared Python entrypoint from a copied workspace after fingerprint-bound, single-use approval. They validate paths, reject symlinks, use the current interpreter's isolated mode, avoid a shell, allowlist process environment variables, and apply candidate changes only to declared JSON configuration keys. Baseline and candidate measurements are independently recorded, then accepted candidates remain isolated for review; the original source is not promoted or overwritten.

**A copied directory is not a security sandbox.** The legacy ML and HTTP runners may still read accessible host files, start other processes, or access the network. Only trusted fixtures or repositories should use those runners on the developer machine. Approval is a policy gate, not containment.

## Declared generic process execution

The `generic_process` adapter requires Linux and bubblewrap and fails closed when containment is unavailable. It uses separate namespaces, denies external network access, exposes repository copies read-only, mounts only exact declared new output files writable, clears ambient environment variables, and runs argv without a shell. CPU, memory, file-size, descriptor and process limits are applied inside the namespace; the parent enforces wall-time and captured-output limits. Windows supports generic preview and preparation but does not automatically dispatch execution to WSL.

These limits are per process rather than aggregate cgroup accounting. System runtimes remain visible, host namespace policy must permit bubblewrap, and this prototype has not been established as a multi-tenant hostile-code service. For untrusted shared workloads, use a separately provisioned, reviewed worker/container or VM with no credentials and aggregate quotas. See [the benchmark protocol](GENERIC_BENCHMARKS.md) for the exact implemented boundary.

CI uses Ubuntu 24.04 and a root-owned copy of bubblewrap at `/usr/local/libexec/ml-analyser-ci/bwrap`. A [CI-only AppArmor profile](../.github/ci/bwrap.apparmor) permits that executable to create user namespaces, following [Ubuntu's per-application namespace policy](https://documentation.ubuntu.com/security/security-features/privilege-restriction/apparmor/). It does not disable AppArmor globally or alter the system bubblewrap executable. A sandbox smoke check runs before the full tests; namespace failures remain errors rather than skipped tests or unsandboxed execution. This runner setup is not installed on user machines by the application.

## Data and credential handling

- Put Token Factory credentials in ignored `.env` or a managed secret store; never in manifests, fixtures, logs, or reports.
- Restrict access to SQLite state and retained workspaces; they may contain repository data and measured outputs.
- The provider sends selected inventory metadata, success contracts, and evidence to the configured endpoint. Review data sensitivity before switching from mock to live inference.
- The browser workbench uses text nodes for dynamic content. The API currently has no authentication; bind it to localhost and do not expose it publicly as-is.

## Operational checks before a shared deployment

1. Add authentication and project-level authorization for approvals, run reads, artifacts, and retained candidates.
2. Move legacy runners behind OS/container isolation; review the generic sandbox boundary and add aggregate quotas before shared hostile-code execution.
3. Move background execution to a durable queue and define recovery behavior for interrupted runs.
4. Record structured run/experiment IDs, durations, provider errors, actual usage, and terminal states; redact secrets and sensitive repository content.
5. Define retention and cleanup policies for SQLite, logs, metrics files, and isolated copies.
6. Run the full CI suite and the read-only `scripts/validate_nebius.py` smoke test with a current Nemotron model before any live demonstration.

The current implementation is intentionally candid about these limits. It does not claim to be a production multi-tenant code-execution service.
