const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");

test("procedural graph is deterministic, finite and bounded at mobile and desktop sizes",async()=>{
  const {makeGraph}=await import("./engine-data.mjs");
  for(const count of [21,240,420]){
    const graph=makeGraph(count);
    assert.deepEqual(graph,makeGraph(count));
    assert.equal(graph.positions.length,count*3);
    assert.equal(graph.scattered.length,count*3);
    assert.equal(graph.colors.length,count*3);
    assert.ok(graph.positions.every(Number.isFinite));
    assert.ok(graph.edges.every(index=>index>=0&&index<count));
    assert.ok(graph.edges.length<count*5);
  }
});
test("fixture comparisons preserve units and distinguish operation counts from timings",async()=>{
  const {FIXTURES,compareFixture}=await import("./engine-data.mjs");
  const cli=compareFixture(FIXTURES.cli);
  assert.equal(cli.delta,-90);assert.equal(cli.percent,90);assert.equal(cli.candidateWidth,10);
  assert.equal(compareFixture(FIXTURES.regression).delta,-2);
  assert.match(FIXTURES.cli.note,/not elapsed time/);
  assert.match(FIXTURES.regression.provenance,/not a live run/);
  assert.equal(compareFixture({...FIXTURES.regression,baseline:0}).percent,null);
});
test("every graph concept has an accessible explanation and scenario states retain uncertainty",async()=>{
  const {CONCEPTS,SCENARIOS,sceneProgress}=await import("./engine-data.mjs");
  assert.equal(new Set(CONCEPTS.map(item=>item.id)).size,7);
  for(const concept of CONCEPTS)assert.ok(concept.title&&concept.text&&concept.position.length===3);
  assert.match(SCENARIOS.inconclusive.text,/too few samples or high variance/i);
  assert.match(SCENARIOS.rejected.text,/correctness guardrail/i);
  assert.equal(sceneProgress(NaN),0);assert.equal(sceneProgress(-1),0);assert.equal(sceneProgress(2),1);
});
test("landing navigation, fixture provenance and local dependencies remain available without WebGL",()=>{
  const html=fs.readFileSync(path.join(__dirname,"landing.html"),"utf8");
  for(const id of ["engine","benchmarks","experiments","approval","evidence"])assert.ok(html.includes(`id="${id}"`));
  for(const link of ["/app","/login","#engine"])assert.ok(html.includes(`href="${link}"`));
  assert.match(html,/FIXTURE REFERENCE · NOT A LIVE RUN/);
  assert.match(html,/id="static-world"/);
  for(const file of ["three.module.min.js","three.core.min.js","gsap.min.js","ScrollTrigger.min.js","THREE-LICENSE.txt","GSAP-LICENSE.txt"])assert.ok(fs.existsSync(path.join(__dirname,"vendor",file)),file);
});
