const test = require("node:test");
const assert = require("node:assert/strict");
const { GOALS, sourceFileAllowed, selectSourceFiles } = require("./onboarding.js");

test("goal presets explain direction with concrete examples; custom stays explicit", () => {
  assert.equal(GOALS.latency.direction, "minimize");
  assert.equal(GOALS.f1.direction, "maximize");
  assert.equal(GOALS.rmse.metric, "validation_rmse");
  assert.match(GOALS.latency.example, /50 ms → 40 ms/);
  assert.equal(GOALS.custom, undefined);
  for (const goal of Object.values(GOALS)) assert.ok(goal.detail && goal.example);
});
test("folder selection filters credentials and generated files across platforms", () => {
  for (const name of ["repo/.env", "repo/.env.local", "repo/.aws/config", "repo/.git/config", "repo/node_modules/x.js", "repo/server.KEY", "repo/client_secret.json"]) assert.equal(sourceFileAllowed(name), false, name);
  assert.equal(sourceFileAllowed("repo/src/main.py"), true);
  const files = [{ webkitRelativePath: "repo/main.py", size: 20 }, { webkitRelativePath: "repo/.env", size: 20 }];
  assert.equal(selectSourceFiles(files).length, 1);
});
test("folder selection enforces count and size boundaries before upload", () => {
  assert.throws(() => selectSourceFiles([]), /No source/);
  assert.throws(() => selectSourceFiles([{webkitRelativePath:"r/a.py", size:3*1024*1024}]), /smaller/);
  assert.throws(() => selectSourceFiles(Array.from({length:1001}, (_, n) => ({webkitRelativePath:`r/${n}.py`, size:1}))), /smaller/);
  assert.throws(() => selectSourceFiles(Array.from({length:21}, (_, n) => ({webkitRelativePath:`r/${n}.py`, size:1024*1024}))), /smaller/);
});
