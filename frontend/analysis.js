const analysisElement = (id) => document.getElementById(id);

function analysisNode(tag, text, className = "") {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}

function analysisCard(title, body, details) {
  const card = analysisNode("article", "", "analysis-card");
  card.append(analysisNode("h4", title), analysisNode("p", body));
  if (details) card.append(analysisNode("small", details));
  return card;
}

function renderRepositoryPreview(result) {
  analysisElement("analysis-output").classList.remove("hidden");
  analysisElement("analysis-status").textContent = `${result.project_id} · ${result.inventory.total_files} files inventoried`;
  analysisElement("analysis-provider").textContent = result.provider;
  const metric = analysisElement("analysis-metric").value.trim();
  const direction = analysisElement("analysis-direction").value;
  const targetText = analysisElement("analysis-target").value.trim();
  const objective = { metric, direction, target: targetText ? Number(targetText) : undefined };
  const guardrailMetric = analysisElement("analysis-guardrail-metric").value.trim();
  const guardrailThreshold = analysisElement("analysis-guardrail-threshold").value.trim();
  const constraints = guardrailMetric && guardrailThreshold ? [{
    metric: guardrailMetric,
    operator: analysisElement("analysis-guardrail-operator").value,
    threshold: Number(guardrailThreshold),
  }] : [];
  analysisElement("analysis-metric-guide").textContent =
    `${metric}: ${describeMetric(metric)} Your selected goal is to ${direction === "minimize" ? "lower" : "raise"} this value. ` +
    "Targets and guardrails are goals; this preview has not tested whether they pass.";

  renderOverview(result.repository_summary, analysisElement("repository-overview"));
  const adapterControls = analysisNode("div");
  for (const adapter of result.repository_summary.adapters) {
    if (adapter.status !== "supported_and_executable") continue;
    const button = analysisNode("button", `Prepare ${adapter.adapter} experiment`, "primary-button");
    button.type = "button";
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        prepared = await api("/prepare", "POST", {
          adapter: adapter.adapter, project_path: analysisElement("analysis-path").value.trim(),
          success_contract: result.success_contract,
        });
        renderPlan();
        setStatus("active", "Declared plan ready for review");
        $("plan-review").scrollIntoView({ behavior: "smooth", block: "center" });
      } catch (error) { showError(error.message); }
      finally { button.disabled = false; }
    });
    adapterControls.append(button);
  }
  analysisElement("repository-overview").append(adapterControls);
  const counts = analysisElement("analysis-counts");
  counts.replaceChildren(...Object.entries(result.inventory.category_counts).map(([category, count]) =>
    analysisNode("span", `${category.replaceAll("_", " ")}: ${count}`)
  ));

  const recorded = analysisElement("analysis-recorded");
  recorded.replaceChildren();
  for (const item of result.evidence) {
    const serialized = item.metadata?.recorded_metrics_json;
    if (!serialized) continue;
    let values;
    try { values = JSON.parse(serialized); } catch { continue; }
    for (const [name, value] of Object.entries(values)) {
      const card = analysisNode("div", "", "recorded-card");
      card.append(
        analysisNode("small", name.replaceAll("_", " ")),
        analysisNode("strong", formatMetricValue(value, name)),
        analysisNode("span", `Prior record: ${item.source}`),
        analysisNode("p", describeMetric(name)),
        analysisNode("p", interpretRecordedValue(value, name, objective, constraints), "recorded-inference")
      );
      recorded.append(card);
    }
  }
  if (recorded.childElementCount) {
    recorded.prepend(analysisNode("p", "Values below came from existing repository files. They were not remeasured in this analysis; compare runs only with matching data, hardware, and benchmark settings.", "recorded-note"));
  }

  const hypotheses = analysisElement("analysis-hypotheses");
  hypotheses.replaceChildren(...result.hypotheses.map((item) =>
    analysisCard(
      `${item.kind} proposal · ${item.statement}`,
      `Test: ${item.proposed_intervention}`,
      `Reject when: ${item.rejection_criteria} · Evidence: ${item.evidence_ids.join(", ")}`
    )
  ));

  const experiments = analysisElement("analysis-experiments");
  experiments.replaceChildren(...result.experiments.map((item) =>
    analysisCard(
      item.title,
      item.procedure.join(" "),
      `Would measure: ${item.measurements.join(", ")} · ${item.status}; not executed`
    )
  ));

  const evidence = analysisElement("analysis-evidence");
  evidence.replaceChildren(...result.evidence.map((item) => {
    const details = document.createElement("details");
    details.className = "analysis-evidence-item";
    details.append(analysisNode("summary", `${item.kind} · ${item.source}`));
    details.id = `evidence-${item.id}`;
    details.append(analysisNode("p", item.claim), analysisNode("pre", JSON.stringify(item, null, 2)));
    return details;
  }));
  analysisElement("analysis-warnings").replaceChildren(
    ...result.warnings.map((warning) => analysisNode("p", warning))
  );
}

analysisElement("analysis-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = analysisElement("analysis-submit");
  const errorBox = analysisElement("analysis-error");
  button.disabled = true;
  button.firstChild.textContent = "Analysing repository ";
  errorBox.classList.add("hidden");
  analysisElement("analysis-output").classList.add("hidden");

  const path = analysisElement("analysis-path").value.trim();
  const metric = analysisElement("analysis-metric").value.trim();
  const target = analysisElement("analysis-target").value.trim();
  const improvement = analysisElement("analysis-improvement").value.trim();
  const guardrailMetric = analysisElement("analysis-guardrail-metric").value.trim();
  const guardrailThreshold = analysisElement("analysis-guardrail-threshold").value.trim();
  if (Boolean(guardrailMetric) !== Boolean(guardrailThreshold)) {
    errorBox.textContent = "Enter both a guardrail metric and its limit, or leave both blank.";
    errorBox.classList.remove("hidden");
    button.disabled = false;
    button.firstChild.textContent = "Analyse repository ";
    return;
  }
  const objective = {
    metric,
    direction: analysisElement("analysis-direction").value,
    minimum_improvement: improvement ? Number(improvement) : 0,
  };
  if (target) objective.target = Number(target);
  const constraints = guardrailMetric && guardrailThreshold
    ? [{ metric: guardrailMetric, operator: analysisElement("analysis-guardrail-operator").value, threshold: Number(guardrailThreshold) }]
    : [];

  try {
    const response = await fetch("/api/v1/runs/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_path: path, success_contract: { objective, constraints } }),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(typeof result.detail === "string" ? result.detail : `Analysis failed (${response.status})`);
    }
    renderRepositoryPreview(result);
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.classList.remove("hidden");
  } finally {
    button.disabled = false;
    button.firstChild.textContent = "Analyse repository ";
  }
});
