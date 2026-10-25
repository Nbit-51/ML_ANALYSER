"use strict";

const PREDICTION_METRICS = {
  f1_macro:{label:"Macro F1",unit:"ratio",explanation:"Higher is better. Average F1 equally across classes on a 0–1 scale; minority classes count as much as majority classes."},
  accuracy:{label:"Accuracy",unit:"ratio",explanation:"Higher is better. The fraction of examples whose predicted label matches the actual label."},
  rmse:{label:"RMSE",unit:"target units",explanation:"Lower is better. Root mean squared error uses the actual target's units and gives larger errors more weight."},
  mae:{label:"MAE",unit:"target units",explanation:"Lower is better. Mean absolute error measures the average size of an error in the actual target's units."},
  precision_macro:{label:"Macro precision",unit:"ratio"},recall_macro:{label:"Macro recall",unit:"ratio"},
  f1_weighted:{label:"Weighted F1",unit:"ratio"},r2:{label:"R²",unit:"score"},
};
function predictionNumber(value) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en", {maximumSignificantDigits:6}).format(value);
}
function predictionIntervalText(report) {
  return `Observed improvement: ${predictionNumber(report.improvement)}. Approximate 95% interval: ${predictionNumber(report.improvement_interval[0])} to ${predictionNumber(report.improvement_interval[1])}. Required: at least ${predictionNumber(report.minimum_improvement)}.`;
}
if (typeof module !== "undefined") module.exports = {PREDICTION_METRICS,predictionNumber,predictionIntervalText};

if (typeof document !== "undefined") {
  const byId = id => document.getElementById(id);
  let displayed = null;
  let inputVersion = 0;
  let pendingLoads = 0;
  let calculating = false;
  function syncButton() { byId("compare-predictions").disabled = calculating || pendingLoads > 0; }
  function node(tag, text, className = "") { const item=document.createElement(tag); item.textContent=text; item.className=className; return item; }
  function error(message) { byId("comparison-error").textContent=message; byId("comparison-error").classList.remove("hidden"); }
  function clearResults() { inputVersion++; displayed=null; byId("comparison-results").classList.add("hidden"); byId("comparison-error").classList.add("hidden"); }
  function updateTask() {
    clearResults();
    const classification=byId("prediction-task").value === "classification";
    byId("prediction-metric").replaceChildren(...(classification ? ["f1_macro","accuracy"] : ["rmse","mae"]).map(name=>{
      const option=node("option",`${PREDICTION_METRICS[name].label} · ${classification ? "higher" : "lower"} is better`); option.value=name; return option;
    }));
    byId("minimum-improvement").value=classification ? "0.01" : "0.1";
    byId("maximum-regression").value=classification ? "0.02" : "0.1";
    byId("regression-label").textContent=classification ? "Maximum cohort accuracy / class recall drop" : "Maximum cohort MAE increase";
    byId("regression-explanation").textContent=classification ? "0.02 allows a drop of two percentage points. A supported cohort or class can reject an otherwise improved model." : "Use the actual target's units. A cohort whose MAE increases beyond this limit rejects the candidate even if overall RMSE improves.";
    updateMetric();
  }
  function updateMetric() { byId("metric-explanation").textContent=PREDICTION_METRICS[byId("prediction-metric").value].explanation; }
  byId("prediction-task").addEventListener("change",updateTask);
  byId("prediction-metric").addEventListener("change",()=>{clearResults();updateMetric();});
  for (const id of ["prediction-csv","minimum-improvement","maximum-regression","minimum-slice-size"]) byId(id).addEventListener("input",clearResults);
  byId("prediction-file").addEventListener("change",async event=>{
    clearResults(); const version=inputVersion; const file=event.target.files[0]; if(!file)return;
    if(file.size>2000000){error("Choose a CSV smaller than 2 MB.");return;}
    pendingLoads++;syncButton();byId("file-status").textContent="Reading CSV…";
    try{const text=await file.text();if(version!==inputVersion)return;
      byId("prediction-csv").value=text; byId("file-status").textContent=`${file.name} · ${file.size.toLocaleString()} bytes loaded. Review the task and rules before comparing.`;
    }catch(problem){if(version===inputVersion)error(problem.message);}finally{pendingLoads--;syncButton();}
  });
  for(const button of document.querySelectorAll("[data-example]")) button.addEventListener("click",async()=>{
    clearResults(); const version=inputVersion; button.disabled=true;pendingLoads++;syncButton();byId("file-status").textContent="Loading illustrative predictions…";
    try{
      const name=button.dataset.example;
      const response=await fetch(`/static/examples/predictions-${name}.csv`); if(!response.ok)throw new Error("Example could not be loaded.");
      const text=await response.text();if(version!==inputVersion)return;
      byId("prediction-task").value=name==="regression-improvement" ? "regression" : "classification"; updateTask();
      byId("prediction-csv").value=text; byId("file-status").textContent="Illustrative synthetic predictions loaded. Click Compare predictions to calculate their scores.";
    }catch(problem){if(version===inputVersion)error(problem.message);}finally{button.disabled=false;pendingLoads--;syncButton();}
  });
  function renderTable(headers, rows) {
    const table=document.createElement("table"),head=document.createElement("thead"),body=document.createElement("tbody"),heading=document.createElement("tr");
    heading.append(...headers.map(text=>node("th",text))); head.append(heading);
    for(const values of rows){const row=document.createElement("tr");row.append(...values.map(text=>node("td",String(text))));body.append(row);}
    table.append(head,body);return table;
  }
  function render(report) {
    displayed=report;
    byId("comparison-title").textContent=`${report.rows.toLocaleString()} paired examples · ${PREDICTION_METRICS[report.primary_metric].label}`;
    byId("comparison-verdict").textContent=report.decision; byId("comparison-verdict").className=`verdict ${report.decision}`;
    byId("comparison-reasons").textContent=report.reasons.join(" "); byId("improvement-interval").textContent=predictionIntervalText(report);
    byId("prediction-metrics").replaceChildren(...Object.keys(report.baseline).map(metric=>{
      const card=node("article","","metric-card"),info=PREDICTION_METRICS[metric];
      const values=node("div","","metric-values"); values.append(node("span",predictionNumber(report.baseline[metric])),node("span",predictionNumber(report.candidate[metric])));
      card.append(node("h3",info.label),values,node("small",`Baseline → Candidate · ${info.unit}`));return card;
    }));
    const failures=report.slices.filter(item=>item.passed===false).length,unchecked=report.slices.filter(item=>!item.checked).length;
    byId("slice-summary").textContent=`${failures} regression limit${failures===1 ? "" : "s"} failed; ${unchecked} slice${unchecked===1 ? "" : "s"} below minimum support. Classification checks cohort accuracy and per-class recall; regression checks cohort MAE.`;
    const table=renderTable(["Slice","Examples","Metric","Baseline","Candidate","Regression","Allowed","Check"],report.slices.map(item=>[
      `${item.kind} · ${item.name}`,item.count,item.metric,predictionNumber(item.baseline),predictionNumber(item.candidate),predictionNumber(item.regression),predictionNumber(item.allowed_regression),!item.checked ? "Low support" : item.passed ? "PASS" : "FAIL",
    ]));
    Array.from(table.tBodies[0].rows).forEach((row,index)=>{row.cells[7].className=report.slices[index].passed===false ? "rejected" : report.slices[index].checked ? "accepted" : "inconclusive";});
    byId("prediction-slices").replaceChildren(table);
    byId("confusion-section").classList.toggle("hidden",report.task!=="classification");
    byId("prediction-confusion").replaceChildren(...Object.entries(report.confusion_matrices).map(([name,matrix])=>{
      const box=document.createElement("div");box.append(node("h3",name==="baseline" ? "Baseline" : "Candidate"));
      const grid=renderTable(["Actual ↓ / Predicted →",...report.labels],matrix.map((row,index)=>[report.labels[index],...row]));
      Array.from(grid.tBodies[0].rows).forEach((row,i)=>Array.from(row.cells).slice(1).forEach((cell,j)=>{if(matrix[i][j])cell.className=i===j ? "correct" : "incorrect";}));box.append(grid);return box;
    }));
    byId("prediction-limitations").replaceChildren(...report.limitations.map(text=>node("li",text)));
    byId("prediction-provenance").textContent=`${report.protocol} · data SHA-256 ${report.dataset_sha256} · report SHA-256 ${report.report_sha256}`;
    byId("comparison-results").classList.remove("hidden"); byId("comparison-results").scrollIntoView({behavior:"smooth",block:"start"});
  }
  byId("prediction-form").addEventListener("submit",async event=>{
    event.preventDefault();if(calculating||pendingLoads)return;clearResults(); const version=inputVersion; calculating=true;syncButton();byId("comparison-status").textContent="Computing paired metrics, slice checks and 200 bootstrap resamples…";
    try{
      const csv=byId("prediction-csv").value;if(!csv.trim())throw new Error("Choose a CSV or load an example first.");
      const response=await fetch("/api/v1/evaluation/compare",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
        task:byId("prediction-task").value,csv_text:csv,primary_metric:byId("prediction-metric").value,
        minimum_improvement:Number(byId("minimum-improvement").value),maximum_slice_regression:Number(byId("maximum-regression").value),minimum_slice_size:Number(byId("minimum-slice-size").value),
      })});
      const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==="string" ? data.detail : "Invalid data or settings. Check the CSV format and numeric limits.");
      if(version!==inputVersion){byId("comparison-status").textContent="Inputs changed during comparison. Compare again with the current data and rules.";return;}
      render(data);byId("comparison-status").textContent="Comparison complete. No model or project code was executed.";
    }catch(problem){if(version===inputVersion){error(problem.message);byId("comparison-status").textContent="Comparison not completed.";}}finally{calculating=false;syncButton();}
  });
  byId("export-comparison").addEventListener("click",()=>{
    if(!displayed)return;const url=URL.createObjectURL(new Blob([JSON.stringify(displayed,null,2)],{type:"application/json"}));
    const link=document.createElement("a");link.href=url;link.download=`ml-analyser-predictions-${displayed.report_sha256.slice(0,12)}.json`;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),0);
  });
  updateTask();
}
