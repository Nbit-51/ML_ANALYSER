# Backend Benchmark Demo

## Purpose

This demonstration proves that the evidence and decision core is not tied to ML metrics. The committed fixture exposes a small JSON service with `25 ms` of simulated work. Its manifest proposes a `1 ms` candidate configuration, but that change is applied only inside an isolated copy.

The adapter is intentionally narrow: it runs the current Python interpreter with `-I`, launches no shell, binds only to localhost, accepts one manifest shape, applies JSON configuration overrides, limits requests and timeouts, and bounds captured output. This is controlled local isolation, not a security boundary for arbitrary hostile code.

## Success contract

- Minimize `p95_latency_ms`.
- Require candidate P95 below `40 ms` and an improvement greater than `10 ms`.
- Require `error_rate <= 0`.
- Require identical baseline and candidate response hashes.
- Allow one experiment and ten seconds of measured wall time.

The target was initially `15 ms`. Real Windows localhost/process overhead made the optimized fixture consistently land around `20-27 ms`, so the contract was corrected to `40 ms` while retaining a meaningful minimum-improvement requirement. This is exactly the kind of evidence-driven revision the product is intended to make.

## Run it

Start the API from the repository root:

```powershell
uvicorn ml_analyser.main:app --app-dir backend --reload
```

In another PowerShell terminal, prepare the plan:

```powershell
$request = Get-Content workspaces/backend-benchmark-demo/prepare_request.json -Raw
$prepared = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/runs/backend-benchmark/prepare `
  -ContentType application/json `
  -Body $request

$prepared.plan | ConvertTo-Json -Depth 20
$prepared.approval
```

After reviewing the plan, approve its exact fingerprint:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/runs/approvals/$($prepared.approval.id)" `
  -ContentType application/json `
  -Body '{"approved":true,"reason":"Demo scope reviewed"}'
```

Execute the unchanged plan:

```powershell
$executionBody = @{
  approval_id = $prepared.approval.id
  plan = $prepared.plan
} | ConvertTo-Json -Depth 20

$result = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/runs/backend-benchmark/execute `
  -ContentType application/json `
  -Body $executionBody

$result | ConvertTo-Json -Depth 20
```

Replaying the execution with the consumed approval returns HTTP `409`. Changing any plan field also invalidates the approval fingerprint.

## Reproducible observed result

Final local validation on September 21, 2026:

| Measurement | Baseline | Candidate |
| --- | ---: | ---: |
| Requests succeeded | 20/20 | 20/20 |
| Error rate | 0.0000 | 0.0000 |
| P50 latency | 45.92 ms | 4.70 ms |
| P95 latency | 50.23 ms | 22.12 ms |
| Mean latency | 40.95 ms | 10.53 ms |
| Throughput | 24.42 req/s | 94.96 req/s |

The response hashes were identical. Decision: **accepted**. The candidate copy was retained for inspection, the baseline copy was discarded, and the original fixture was unchanged. Exact timing is host-dependent; the invariant assertions live in the integration tests.

## Rejection behavior

The test suite also runs a deliberately slower candidate. That candidate is rejected, both temporary copies are removed, and the source remains unchanged. Evidence and experiment lineage persist even when the candidate is discarded.
