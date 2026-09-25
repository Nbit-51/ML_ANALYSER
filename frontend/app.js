const DEMOS = {
  "ml-training": {
    project: "ml-training-demo",
    objective: { metric: "f1", direction: "maximize", target: 0.9, minimum_improvement: 0.1 },
    constraints: [
      { metric: "recall", operator: "gte", threshold: 1.0 },
      { metric: "accuracy", operator: "gte", threshold: 0.9 },
    ],
    budget: { max_wall_clock_seconds: 10, max_experiments: 1 },
    heading: "Validation F1",
  },
  "backend-benchmark": {
    project: "backend-benchmark-demo",
    objective: { metric: "p95_latency_ms", direction: "minimize", target: 40, minimum_improvement: 10 },
    constraints: [
      { metric: "error_rate", operator: "lte", threshold: 0 },
      { metric: "response_hash_matches", operator: "eq", threshold: 1 },
    ],
    budget: { max_wall_clock_seconds: 10, max_experiments: 1 },
    heading: "P95 latency",
  },
};

const STAGES = [
  "ingesting", "diagnosing", "hypothesizing", "designing", "selecting",
  "awaiting_approval", "executing", "measuring", "deciding", "reporting", "completed",
];
const LABELS = {
  ingesting: "Inventory repository",
  diagnosing: "Inspect project state",
  hypothesizing: "Form falsifiable hypothesis",
  designing: "Compile controlled experiment",
  selecting: "Select candidate",
  awaiting_approval: "Await exact scope approval",
  executing: "Run isolated baseline & candidate",
  measuring: "Capture measurements",
  deciding: "Check objective & guardrails",
  reporting: "Persist evidence & report",
  completed: "Run complete",
  failed: "Run failed",
};

const $ = (id) => document.getElementById(id);
let selected = "ml-training";
let prepared = null;
let pollTimer = null;

function element(tag, text, className = "") {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}

function showError(message) {
  $("error-box").textContent = message;
  $("error-box").classList.remove("hidden");
  setStatus("failed", "Action needs attention");
}

function clearError() { $("error-box").classList.add("hidden"); }

function setStatus(kind, label) {
  $("status-dot").className = `status-dot ${kind}`;
  $("status-label").textContent = label;
}

function renderContract() {
  const demo = DEMOS[selected];
  const contract = $("contract");
  contract.replaceChildren(element("div", "SUCCESS CONTRACT", "contract-title"));
  const rows = [
    ["Objective", `${demo.heading} ${demo.objective.direction === "maximize" ? "≥" : "≤"} ${demo.objective.target}`],
    ["Minimum improvement", `${demo.objective.minimum_improvement} ${demo.objective.metric === "p95_latency_ms" ? "ms" : "points"}`],
    ...demo.constraints.map((item) => [item.metric, `${{gte:"≥",lte:"≤",eq:"="}[item.operator]} ${item.threshold}`]),
    ["Budget", `≤ ${demo.budget.max_wall_clock_seconds}s · ${demo.budget.max_experiments} experiment`],
  ];
  for (const [name, value] of rows) {
    const row = element("div", "", "contract-row");
    row.append(element("strong", name), element("span", value));
    contract.append(row);
  }
}

function renderTimeline(events = []) {
  const list = $("timeline");
  const latest = events.at(-1);
  list.replaceChildren();
  for (const stage of STAGES) {
    const reached = events.includes(stage);
    const node = element("li", LABELS[stage], reached ? (stage === latest ? "current" : "done") : "");
    list.append(node);
  }
  if (latest === "failed") list.append(element("li", LABELS.failed, "current"));
}

function renderPlan() {
  const plan = prepared.plan;
  $("plan-review").classList.remove("hidden");
  $("plan-title").textContent = plan.experiment.title;
  $("hypothesis").textContent = plan.hypothesis.statement;
  $("rejection").textContent = plan.hypothesis.rejection_criteria;
  $("risk-pill").textContent = `${prepared.approval.risk_level.toUpperCase()} RISK`;
  $("run-id").textContent = plan.run_id.slice(0, 8);
  $("changes").replaceChildren(...plan.experiment.change_summary.map((change) => element("li", change)));
  renderTimeline(["ingesting", "diagnosing", "hypothesizing", "designing", "selecting", "awaiting_approval"]);
}

async function api(path, method = "GET", body = undefined) {
  const response = await fetch(`/api/v1/runs${path}`, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : `Request failed (${response.status})`);
  return payload;
}

async function prepare() {
  clearError();
  $("prepare-button").disabled = true;
  setStatus("active", "Inspecting project");
  const demo = DEMOS[selected];
  try {
    prepared = await api(`/${selected}/prepare`, "POST", {
      project_path: demo.project,
      project_id: demo.project,
      success_contract: {
        objective: demo.objective,
        constraints: demo.constraints,
        budget: demo.budget,
      },
    });
    renderPlan();
    setStatus("active", "Plan ready for approval");
  } catch (error) { showError(error.message); }
  finally { $("prepare-button").disabled = false; }
}

async function approveAndStart() {
  if (!prepared) return;
  clearError();
  $("approve-button").disabled = true;
  try {
    const approvalId = prepared.approval.id;
    await api(`/approvals/${approvalId}`, "POST", { approved: true, reason: "Approved in demo workbench" });
    const started = await api(`/${selected}/start`, "POST", { approval_id: approvalId, plan: prepared.plan });
    $("plan-review").classList.add("hidden");
    setStatus("active", "Run queued");
    sessionStorage.setItem("ml-analyser-live-run", started.run_id);
    await pollRun(started.run_id);
  } catch (error) { showError(error.message); $("approve-button").disabled = false; }
}

function metricValue(result, metric, label) {
  const observation = result[label];
  if (observation.metrics) return observation.metrics[metric];
  return observation[metric];
}

function formatMetric(value, metric) {
  if (metric === "throughput_requests_per_second" && typeof value === "number") {
    return `${value.toFixed(1)} req/s`;
  }
  return formatMetricValue(value, metric);
}

function renderResult(result) {
  $("results").classList.remove("hidden");
  const decision = result.decision.status;
  $("decision-pill").className = `decision-pill ${decision}`;
  $("decision-pill").textContent = decision.toUpperCase();
  $("decision-reason").textContent = result.decision.reason;
  const metrics = $("metrics");
  metrics.replaceChildren();
  const metricNames = selected === "ml-training"
    ? ["f1", "accuracy", "precision", "recall"]
    : ["p95_latency_ms", "p50_latency_ms", "error_rate", "throughput_requests_per_second"];
  for (const name of metricNames) {
    const card = element("div", "", "metric");
    const baselineValue = metricValue(result, name, "baseline");
    const candidateValue = metricValue(result, name, "candidate");
    card.append(element("span", name.replaceAll("_", " "), "metric-label"));
    card.append(element("strong", formatMetric(candidateValue, name), "improved"));
    card.append(element("small", `Baseline ${formatMetric(baselineValue, name)}`));
    card.append(element("small", describeMetric(name), "metric-meaning"));
    card.append(element("small", interpretMetricChange(baselineValue, candidateValue, name), "metric-meaning"));
    metrics.append(card);
  }
  $("evidence").replaceChildren(...result.evidence.map((item) => {
    const node = element("div", "", "evidence-item");
    node.append(element("strong", item.kind.toUpperCase()), element("span", item.claim), element("span", item.id));
    return node;
  }));
  $("lineage").replaceChildren(...result.experiments.map((item) => {
    const node = element("div", "", "lineage-item");
    node.append(element("strong", item.title), element("span", `${item.status} · ${item.id}`));
    return node;
  }));
  $("disposition").textContent = result.disposition === "retained"
    ? "Candidate retained in the isolated execution workspace. Original project unchanged."
    : "Candidate discarded after evaluation. Original project unchanged.";
}

async function pollRun(runId) {
  if (pollTimer) clearTimeout(pollTimer);
  try {
    const snapshot = await api(`/live/${runId}`);
    selected = snapshot.adapter === "ml_training" ? "ml-training" : "backend-benchmark";
    renderContract();
    $("run-id").textContent = runId.slice(0, 8);
    renderTimeline(snapshot.events);
    if (snapshot.status === "completed") {
      setStatus("success", "Run complete · measured decision recorded");
      renderResult(snapshot.result);
      sessionStorage.removeItem("ml-analyser-live-run");
    } else if (snapshot.status === "failed") {
      showError(snapshot.error || "The run failed. Inspect the API logs.");
      sessionStorage.removeItem("ml-analyser-live-run");
    } else {
      setStatus("active", `${snapshot.state.replaceAll("_", " ")} · ${snapshot.status}`);
      pollTimer = setTimeout(() => pollRun(runId), 850);
    }
  } catch (error) { showError(error.message); }
}

document.querySelectorAll('input[name="adapter"]').forEach((radio) => {
  radio.addEventListener("change", () => {
    if (pollTimer) clearTimeout(pollTimer);
    selected = radio.value;
    prepared = null;
    document.querySelectorAll(".adapter-card").forEach((card) => card.classList.toggle("selected", card.contains(radio)));
    $("plan-review").classList.add("hidden");
    $("results").classList.add("hidden");
    $("run-id").textContent = "";
    clearError();
    setStatus("idle", "Ready to prepare");
    renderContract();
    renderTimeline();
  });
});
$("prepare-button").addEventListener("click", prepare);
$("approve-button").addEventListener("click", approveAndStart);
renderContract();
renderTimeline();
const previousRun = sessionStorage.getItem("ml-analyser-live-run");
if (previousRun) pollRun(previousRun);
