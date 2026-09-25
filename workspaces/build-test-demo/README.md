# build-test-demo

Declared test_suite fixture. Baseline redundantly recomputes the same sum 100 times; candidate computes it 10 times. `work_units` counts actual computations; `elapsed_ms` is wall time, not the acceptance objective. No external dependencies. Linux bubblewrap required. Set candidate `incorrect` to true to demonstrate rejection, or repetitions to 1 to demonstrate inconclusive evidence.
