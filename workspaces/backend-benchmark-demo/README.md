# Backend Benchmark Demo

This fixture proves that the evidence engine is not ML-specific. It exposes a deterministic localhost JSON endpoint with a deliberately slow configuration (`25 ms` of simulated work per request). The manifest declares a candidate configuration (`1 ms`) that is applied only inside an isolated candidate copy.

The workflow requires three API calls: prepare the fingerprinted plan, explicitly approve it, and execute the unchanged approved plan. The adapter benchmarks baseline and candidate copies, verifies identical response hashes, evaluates latency/error/budget constraints, retains an accepted candidate workspace, and never modifies this original fixture.

This is a controlled proof of the backend adapter contract, not an OS-level sandbox for arbitrary untrusted repositories.
