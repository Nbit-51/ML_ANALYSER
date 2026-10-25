const test = require("node:test");
const assert = require("node:assert/strict");
const { summarizeAttempt } = require("./lab.js");

test("an improved objective retains a rejected correctness verdict", () => {
  const summary = summarizeAttempt({
    baseline: { reference_lookups: 120 }, candidate: { reference_lookups: 5, incorrect_quotes: 100 },
    decision: { status: "rejected" }, proposal: { cache_fields: ["sku"] },
  });
  assert.equal(summary.status, "rejected");
  assert.equal(summary.work, "120 → 5");
  assert.equal(summary.errors, 100);
  assert.ok(summary.reduction > 95);
});

test("zero baseline does not invent a percentage improvement", () => {
  const summary = summarizeAttempt({
    baseline: { reference_lookups: 0 }, candidate: { reference_lookups: 0, incorrect_quotes: 0 },
    decision: { status: "inconclusive" }, proposal: { cache_fields: ["tenant", "sku", "currency"] },
  });
  assert.equal(summary.reduction, null);
  assert.equal(summary.status, "inconclusive");
});
