const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = readFileSync(path.join(__dirname, "metrics.js"), "utf8");
const metrics = vm.runInNewContext(
  `${source}\n({ describeMetric, formatMetricValue, interpretMetricChange, interpretRecordedValue })`
);

test("explains classification, regression, and latency metrics", () => {
  assert.match(metrics.describeMetric("f1"), /precision and recall/);
  assert.match(metrics.describeMetric("validation_rmse"), /prediction error/);
  assert.match(metrics.describeMetric("p50_latency_ms"), /median time/);
  assert.match(metrics.describeMetric("custom_score"), /project-defined metric/);
});

test("preserves useful precision in recorded values", () => {
  assert.equal(metrics.formatMetricValue(9.4825, "p50_latency_ms"), "9.4825 ms");
  assert.equal(metrics.formatMetricValue(4.6193599700927734e-7, "max_abs"), "4.62e-7");
});

test("interprets improvement only in the chosen direction", () => {
  assert.match(metrics.interpretMetricChange(0.7, 0.8, "f1"), /favorable/);
  assert.match(metrics.interpretMetricChange(10, 12, "p95_latency_ms"), /unfavorable/);
  assert.match(metrics.interpretMetricChange(2, 3, "custom_score"), /check this project's metric definition/);
});

test("marks prior target and guardrail comparisons as non-final", () => {
  const objective = { metric: "p50_latency_ms", direction: "minimize", target: 9 };
  const constraints = [{ metric: "max_abs", operator: "lte", threshold: 1e-5 }];
  assert.match(
    metrics.interpretRecordedValue(9.4825, "p50_latency_ms", objective, constraints),
    /misses the target.*Re-measure/
  );
  assert.match(
    metrics.interpretRecordedValue(4.62e-7, "max_abs", objective, constraints),
    /within the limit.*not a fresh safety check/
  );
});
