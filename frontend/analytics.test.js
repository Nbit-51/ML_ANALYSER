const test = require("node:test");
const assert = require("node:assert/strict");
const { comparisonData, chartScale, distributionData, guardrailData, lineageData,
  reliabilityData, unitValue } = require("./analytics.js");

function result() {
  return { success_contract: { objective: { metric: "custom", direction: "minimize", target: 3, minimum_improvement: 1 },
    constraints: [{ metric: "guard", operator: "gte", threshold: 5 }] },
    measurements: { baseline: [{ metric: "custom", value: 4, unit: "widgets", evidence_ids: ["a"], raw_samples: [3, 4, 5] }],
      candidate: [{ metric: "custom", value: 2, unit: "widgets", evidence_ids: ["b"], raw_samples: [1, 2, 3],
        warmup_count: 1, failed_sample_count: 0, summary: { coefficient_of_variation: .5 } }] },
    decision: { status: "accepted", objective: { passed: true }, constraints: [{ metric: "guard", passed: false }] } };
}

test("custom metrics use contract direction, explicit units and deltas", () => {
  const row = comparisonData(result())[0];
  assert.equal(row.name, "custom"); assert.equal(row.direction, "minimize");
  assert.equal(row.delta, -2); assert.equal(row.percentage_delta, -50);
  assert.deepEqual(row.evidence_ids, ["a", "b"]);
  assert.equal(unitValue(2, "unfamiliar-unit"), "2 unfamiliar-unit");
  assert.equal(unitValue(null), "—");
});
test("zero, missing values and mismatched units never produce misleading percentages", () => {
  const data = result(); data.measurements.baseline[0].value = 0;
  assert.equal(comparisonData(data)[0].percentage_delta, null);
  data.measurements.candidate[0].unit = "other";
  assert.equal(comparisonData(data)[0].delta, null);
  data.measurements.baseline = [];
  assert.equal(comparisonData(data)[0].baseline, null);
  data.success_contract.objective.metric = "something_else";
  assert.equal(comparisonData(data)[0].direction, null);
});
test("guardrails and objective preserve pass fail and inconclusive", () => {
  const data = result();
  assert.deepEqual(guardrailData(data).map(r => r.status), ["pass", "fail"]);
  data.decision = { status: "inconclusive" };
  assert.deepEqual(guardrailData(data).map(r => r.status), ["inconclusive", "inconclusive"]);
});
test("distributions share bin boundaries and exclude invalid data", () => {
  const bins = distributionData([1, 2, 3, NaN], [1, 1, 3], 3);
  assert.equal(bins.baseline.reduce((a, b) => a + b), 3);
  assert.equal(bins.candidate.reduce((a, b) => a + b), 3);
  assert.equal(bins.min, 1); assert.equal(bins.max, 3);
  assert.equal(distributionData([], []), null);
  assert.deepEqual(distributionData([0], [0], 2).baseline, [1, 0]);
  assert.equal(chartScale([-2, 4]).position(-2), 8);
  assert.equal(chartScale([-2, 4]).position(4), 292);
});
test("lineage lays out a branching DAG and retains accepted/rejected/inconclusive outcomes", () => {
  const data = lineageData([{ id: "root", status: "measured" }, ...["accepted", "rejected", "inconclusive"]
    .map((status, i) => ({ id: `n${i}`, parent_experiment_id: "root", status }))]);
  assert.equal(data.edges.length, 3);
  assert.equal(data.nodes[1].x, data.nodes[2].x);
  assert.notEqual(data.nodes[1].y, data.nodes[2].y);
  assert.throws(() => lineageData([{ id: "a", parent_experiment_id: "a" }]), /cycle/);
});
test("reliability is explicit about variance and environment", () => {
  const data = result(); data.benchmark_reliability = { status: "inconclusive", reasons: ["high variance"], environment_compatible: false };
  const reliability = reliabilityData(data);
  assert.equal(reliability.environment, "Mismatch");
  assert.equal(reliability.rows[1].cv, .5);
  assert.equal(reliability.rows[1].comparison_samples, 3);
  assert.equal(reliability.rows[1].comparison_cv, .5);
  assert.deepEqual(reliability.reasons, ["high variance"]);
  assert.equal(reliabilityData({}).status, "not_assessed");
});
