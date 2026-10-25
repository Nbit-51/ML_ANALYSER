const test = require("node:test");
const assert = require("node:assert/strict");
const { describeExecutionPlan } = require("./plans.js");

function plan(direction = "maximize", metric = "f1") {
  return {
    manifest: { entrypoint: "train.py", config_file: "config.json", candidate_overrides: { epochs: 250, learning_rate: 0.2 } },
    experiment: { command: ["python-isolated", "train.py"], change_summary: ["Invented change: learning_rate 0.05"] },
    hypothesis: { statement: "Use learning_rate 0.05", rejection_criteria: "Require invented improvement 0.02" },
    success_contract: {
      objective: { metric, direction, minimum_improvement: 0.1, target: 0.9 },
      constraints: [{ metric: "recall", operator: "gte", threshold: 1, tolerance: 0 }],
      budget: { max_wall_clock_seconds: 10, max_cost_usd: null },
    },
  };
}

test("approval describes the executed overrides and contract despite conflicting model prose", () => {
  const review = describeExecutionPlan(plan());
  assert.ok(review.changes.includes("Set learning_rate to 0.2 in config.json"));
  assert.ok(review.criteria.includes("Candidate f1 ≥ baseline f1 + 0.1."));
  assert.ok(review.criteria.includes("Candidate f1 ≥ 0.9."));
  assert.ok(review.criteria.includes("Guardrail: recall ≥ 1."));
  assert.ok(review.criteria.includes("Budget: wall clock seconds ≤ 10."));
  assert.doesNotMatch(JSON.stringify(review), /0\.05|0\.02|Invented/);
});

test("minimization uses the actual RMSE reduction and allows an exact zero target", () => {
  const item = plan("minimize", "validation_rmse");
  item.success_contract.objective.target = 0;
  const review = describeExecutionPlan(item);
  assert.ok(review.criteria.includes("Candidate validation_rmse ≤ baseline validation_rmse − 0.1."));
  assert.ok(review.criteria.includes("Candidate validation_rmse ≤ 0."));
});

test("process plans preserve scalar types, guardrail tolerance and an unset target", () => {
  const item = plan();
  delete item.manifest.entrypoint;
  item.experiment.command = ["python3", "harness.py"];
  item.manifest.candidate_overrides = { enabled: false, label: "0.05", limit: null };
  item.success_contract.objective.target = null;
  item.success_contract.constraints = [{ metric: "signature", operator: "eq", threshold: 1, tolerance: 0.001 }];
  const review = describeExecutionPlan(item);
  assert.match(review.summary, /python3 harness\.py/);
  assert.ok(review.changes.includes('Set label to "0.05" in config.json'));
  assert.ok(review.changes.includes("Set enabled to false in config.json"));
  assert.ok(review.changes.includes("Set limit to null in config.json"));
  assert.ok(review.criteria.includes("Guardrail: signature = 1 (tolerance 0.001)."));
  assert.equal(review.criteria.filter(line => line.startsWith("Candidate")).length, 1);
  assert.match(review.verdictRule, /unreliable.*inconclusive/);
});
