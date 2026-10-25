const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const {PREDICTION_METRICS,predictionNumber,predictionIntervalText}=require("./evaluate.js");
test("classification and regression metrics explain their actual scale and direction",()=>{
  assert.match(PREDICTION_METRICS.f1_macro.explanation,/Higher.*equally.*0–1/);
  assert.match(PREDICTION_METRICS.rmse.explanation,/Lower.*units.*larger errors/);
  assert.equal(PREDICTION_METRICS.mae.unit,"target units");
  assert.equal(predictionNumber(null),"—");assert.equal(predictionNumber(0),"0");assert.equal(predictionNumber(0.000001),"0.000001");
});
test("uncertainty interval preserves zero crossing rather than implying guaranteed improvement",()=>{
  const explanation=predictionIntervalText({improvement:0.1,improvement_interval:[-0.03,0.2],minimum_improvement:0.01});
  assert.match(explanation,/-0\.03 to 0\.2/);assert.match(explanation,/Required: at least 0\.01/);
  assert.doesNotMatch(explanation,/% improvement|significant|guarantee/);
});
function loadEvaluator(exampleButtons=[]){
  const elements=new Map();const requests=[];
  function element(){const classes=new Set();return {value:"",textContent:"",listeners:new Map(),
    classList:{add:name=>classes.add(name),remove:name=>classes.delete(name),contains:name=>classes.has(name)},
    addEventListener(name,handler){this.listeners.set(name,handler);},replaceChildren(...children){this.value=children[0]?.value||"";},
  };}
  const buttons=exampleButtons.map(name=>Object.assign(element(),{dataset:{example:name}}));
  const document={getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);},createElement:element,querySelectorAll:()=>buttons};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,"evaluate.js"),"utf8"),{document,Intl,fetch:url=>new Promise(resolve=>{requests.push({url,resolve});})});
  return {document,requests,buttons};
}
test("changing a dataset while a request is pending cannot display the old report",async()=>{
  const {document,requests}=loadEvaluator();
  document.getElementById("prediction-task").value="classification";
  document.getElementById("prediction-csv").value="actual,baseline,candidate\na,a,a\nb,b,b\n";
  const pending=document.getElementById("prediction-form").listeners.get("submit")({preventDefault(){}});
  document.getElementById("prediction-csv").value="different dataset";
  document.getElementById("prediction-csv").listeners.get("input")();
  requests[0].resolve({ok:true,json:async()=>({rows:2})});await pending;
  assert.equal(document.getElementById("comparison-results").classList.contains("hidden"),true);
  assert.match(document.getElementById("comparison-status").textContent,/Inputs changed/);
  assert.equal(document.getElementById("compare-predictions").disabled,false);
});
test("a pending CSV example cannot accidentally compare the previous dataset",async()=>{
  const {document,requests,buttons}=loadEvaluator(["hidden-regression"]);
  document.getElementById("prediction-csv").value="old data";
  const loading=buttons[0].listeners.get("click")();
  assert.equal(document.getElementById("compare-predictions").disabled,true);
  await document.getElementById("prediction-form").listeners.get("submit")({preventDefault(){}});
  assert.equal(requests.length,1);
  requests[0].resolve({ok:true,text:async()=>"new paired data"});await loading;
  assert.equal(document.getElementById("prediction-csv").value,"new paired data");
  assert.equal(document.getElementById("compare-predictions").disabled,false);
});
