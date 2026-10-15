const test = require("node:test");
const assert = require("node:assert/strict");
const {reportRowSummary} = require("./history.js");

test("saved reports preserve every verdict and custom metric name", () => {
  for (const [decision, label] of [["accepted","Accepted"],["rejected","Rejected"],["inconclusive","Inconclusive"]]) {
    assert.equal(reportRowSummary({project_id:"My repository",metric:"custom_cost",decision}),`My repository · custom_cost · ${label}`);
  }
  assert.match(reportRowSummary({project_id:"p",metric:"m",decision:"unexpected"}),/Unknown decision/);
});
