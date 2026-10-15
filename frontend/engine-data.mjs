export const CONCEPTS = [
  {id:"repository",number:"01",label:"Repository",tag:"READ-ONLY INVENTORY",title:"Inspect before you infer.",text:"Inventory files, detect capabilities and select bounded source excerpts. Static signals describe what exists; they do not establish that a benchmark ran.",position:[-2.9,1.2,.2]},
  {id:"baseline",number:"02",label:"Baseline",tag:"THE CONTROL",title:"Keep a point of comparison.",text:"Run the original configuration in an isolated copy. Compare the same workload, metrics and environment with the candidate.",position:[-.6,2.1,.5]},
  {id:"hypothesis",number:"03",label:"Hypothesis",tag:"NEMOTRON REASONING",title:"A claim that can be disproved.",text:"Nemotron 3 Super proposes a falsifiable explanation grounded in evidence IDs. A predicted improvement remains a hypothesis until measured.",position:[2.1,1.9,-.3]},
  {id:"approval",number:"04",label:"Approval",tag:"HUMAN AUTHORIZATION",title:"One exact plan. One approval.",text:"Approval binds the source fingerprint, contract and declared intervention. Changed plans and replayed approvals cannot authorize another experiment.",position:[3.1,-.2,.8]},
  {id:"experiment",number:"05",label:"Experiment",tag:"CONTROLLED INTERVENTION",title:"Change one declared configuration.",text:"Execute the baseline and candidate through a compatible adapter. Generic process rounds alternate order, record warm-ups and retain raw samples.",position:[1.2,-2.1,-.2]},
  {id:"guardrails",number:"06",label:"Guardrails",tag:"DETERMINISTIC EVALUATION",title:"Faster is only part of better.",text:"Check correctness, the objective and applicable budgets. Failed checks reject the candidate; insufficient or unstable evidence can make the result inconclusive.",position:[-1.2,-2.1,.6]},
  {id:"evidence",number:"07",label:"Evidence",tag:"PERSISTED PROVENANCE",title:"Leave a trail you can inspect.",text:"Measurements, decisions, reports and experiment lineage remain tied to persisted evidence. Accepted candidates remain in isolated copies for review.",position:[-3,-.8,-.5]},
];
export const SCENARIOS = {
  accepted:{label:"Accepted",color:"#7df6e9",title:"Improvement, with the checks intact.",text:"Illustrative outcome: the objective improves, correctness passes and repeated measurements satisfy reliability rules."},
  rejected:{label:"Rejected",color:"#f3b36b",title:"A faster wrong answer is still wrong.",text:"Illustrative outcome: a correctness guardrail fails. The candidate is rejected and its workspace is discarded."},
  inconclusive:{label:"Inconclusive",color:"#b69bff",title:"Uncertainty is a useful result.",text:"Illustrative outcome: too few samples or high variance undermines a required comparison. Gather better evidence before accepting."},
};
export const FIXTURES = {
  regression:{label:"Prediction error",metric:"validation_rmse",unit:"target units",direction:"minimize",baseline:2,candidate:0,target:.1,baselineLabel:"bias = 2",candidateLabel:"bias = 0",source:"workspaces/ml-regression-demo/train.py",provenance:"Reference values calculated by the committed deterministic fixture. Four numeric targets; this is not a live run.",check:"Same four target values",note:"A 100% reduction in this fixture's error; it is not a claim about a trained production model."},
  cli:{label:"Redundant work",metric:"work_units",unit:"operations",direction:"minimize",baseline:100,candidate:10,target:20,baselineLabel:"repeats = 100",candidateLabel:"repeats = 10",source:"workspaces/cli-benchmark-demo/harness.py",provenance:"Reference operation counts from the declared CLI harness. The checksum is preserved; actual timings depend on the host.",check:"Matching workload checksum",note:"90% fewer instrumented repeated operations. Operation count is not elapsed time or a measured speedup."},
};
export function compareFixture(fixture) {
  const delta=fixture.candidate-fixture.baseline;
  return {delta,percent:fixture.baseline===0?null:Math.abs(delta/fixture.baseline)*100,
    favorable:fixture.direction==="minimize"?delta<0:delta>0,
    baselineWidth:fixture.baseline/Math.max(fixture.baseline,fixture.candidate,1)*100,
    candidateWidth:fixture.candidate/Math.max(fixture.baseline,fixture.candidate,1)*100};
}
export function seededRandom(seed=51) {
  let value=seed>>>0;
  return ()=>{value=(Math.imul(value,1664525)+1013904223)>>>0;return value/4294967296;};
}
export function makeGraph(count=420,seed=51) {
  const random=seededRandom(seed), positions=[], scattered=[],colors=[],edges=[];
  for(let i=0;i<count;i++) {
    const ring=Math.floor(i/60),angle=(i%60)/60*Math.PI*2+ring*.43;
    const radius=1.7+random()*1.1;
    positions.push(Math.cos(angle)*radius,Math.sin(angle)*radius*.78,(ring-3)*.36+(random()-.5)*.28);
    scattered.push((random()-.5)*22,(random()-.5)*16,(random()-.5)*15);
    const violet=random()>.74;
    colors.push(violet?.5:.2,violet?.34:.78,violet?1:.86);
    if(i+1<count && i%60!==59) edges.push(i,i+1);
    if(i>=60 && i%3===0) edges.push(i,i-60);
    if(i%8===0) edges.push(i,(i+21)%count);
  }
  return {positions,scattered,colors,edges};
}
export function sceneProgress(value) { return Math.max(0,Math.min(1,Number.isFinite(value)?value:0)); }
