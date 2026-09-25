"use strict";

function svgNode(tag, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  return node;
}

function metricChart(metric) {
  const svg = svgNode("svg", { viewBox: "0 0 300 66", role: "img",
    "aria-label": `${metric.label}: baseline ${metric.baseline}, candidate ${metric.candidate} ${metric.unit || ""}` });
  const scale = chartScale([metric.baseline, metric.candidate]);
  for (const [index, value] of [metric.baseline, metric.candidate].entries()) {
    if (!Number.isFinite(value)) continue;
    const start = scale.position(0), end = scale.position(value);
    svg.append(svgNode("rect", { x: Math.min(start, end), y: 10 + index * 26,
      width: Math.max(1, Math.abs(end - start)), height: 17, rx: 3,
      class: index ? "candidate-bar" : "baseline-bar" }));
  }
  return svg;
}

function renderMetrics(result) {
  const target = $("metrics");
  target.replaceChildren();
  for (const metric of comparisonData(result)) {
    const card = element("article", "", "metric");
    card.append(element("span", `${metric.label} · ${metric.unit || "unit not declared"}`, "metric-label"),
      element("strong", unitValue(metric.candidate, metric.unit)), metricChart(metric),
      element("small", `Baseline ${unitValue(metric.baseline, metric.unit)} · Candidate ${unitValue(metric.candidate, metric.unit)}`),
      element("small", `Δ ${unitValue(metric.delta, metric.unit)} · ${unitValue(metric.percentage_delta, "%")}`),
      element("small", metric.direction ? `${metric.direction} · declared direction` : "Direction not declared"));
    const a = result.measurements?.baseline.find(m => m.metric === metric.name);
    const b = result.measurements?.candidate.find(m => m.metric === metric.name);
    const distribution = distributionData(a?.raw_samples, b?.raw_samples);
    if (distribution) {
      const plot = svgNode("svg", { viewBox: "0 0 300 76", role: "img", "aria-label": "Sample histogram: baseline blue, candidate teal" });
      const max = Math.max(...distribution.baseline, ...distribution.candidate, 1);
      for (let i = 0; i < distribution.baseline.length; i++) {
        for (const [j, variant] of ["baseline", "candidate"].entries()) {
          const height = distribution[variant][i] / max * 65;
          plot.append(svgNode("rect", { x: i * 24 + j * 10, y: 70 - height,
            width: 9, height, class: `${variant}-bar` }));
        }
      }
      card.append(plot, element("small", `Distribution ${unitValue(distribution.min, metric.unit)} — ${unitValue(distribution.max, metric.unit)}; n=${a?.raw_samples.length || 0} / ${b?.raw_samples.length || 0}`));
    }
    const provenance = element("details");
    provenance.append(element("summary", "Measurement provenance"));
    for (const id of metric.evidence_ids) {
      const link = element("a", id); link.href = `#evidence-${id}`; provenance.append(link);
    }
    provenance.append(element("pre", JSON.stringify({ baseline: a, candidate: b }, null, 2)));
    card.append(provenance); target.append(card);
  }
}

function renderGuardrails(result) {
  const table = element("table", "", "guardrail-table");
  const header = element("tr");
  ["Rule", "Baseline", "Candidate", "Threshold / improvement", "Result"].forEach(t => header.append(element("th", t)));
  table.append(header);
  for (const row of guardrailData(result)) {
    const tr = element("tr");
    [ `${row.metric} · ${row.operator}`, unitValue(row.baseline), unitValue(row.candidate),
      `${row.threshold}${row.minimum_improvement !== undefined ? ` · Δ ≥ ${row.minimum_improvement}` : ""}`,
      row.status.toUpperCase()].forEach((value, index) => tr.append(element("td", value, index === 4 ? row.status : "")));
    table.append(tr);
  }
  $("guardrails").replaceChildren(table);
}

function renderReliability(result) {
  const data = reliabilityData(result), target = $("reliability");
  target.replaceChildren(element("strong", data.status.replaceAll("_", " ").toUpperCase()),
    element("p", `Environment: ${data.environment}. No statistical significance test performed.`));
  for (const reason of data.reasons) target.append(element("p", reason, "inconclusive"));
  for (const row of data.rows) target.append(element("p",
    `${row.variant} · ${row.metric}: ${row.warmup} warm-ups, ${row.samples} raw samples, ${row.failed} failures. Raw CV ${unitValue(row.cv === null ? null : row.cv * 100, "%")}; reliability uses ${row.comparison_samples} observations with CV ${unitValue(row.comparison_cv === null ? null : row.comparison_cv * 100, "%")}.`));
}

function renderLineage(result) {
  const data = lineageData(result.experiments), target = $("lineage");
  const width = Math.max(480, ...data.nodes.map(n => n.x + 220));
  const height = Math.max(125, ...data.nodes.map(n => n.y + 90));
  const svg = svgNode("svg", { viewBox: `0 0 ${width} ${height}`, role: "group", "aria-label": "Experiment lineage" });
  for (const edge of data.edges) {
    const from = data.nodes.find(n => n.id === edge.from), to = data.nodes.find(n => n.id === edge.to);
    svg.append(svgNode("line", { x1: from.x + 205, y1: from.y + 30, x2: to.x, y2: to.y + 30, stroke: "#667d98", "stroke-width": 2 }));
  }
  const detail = element("pre", "Select an experiment to inspect its parent, hypothesis, measurements and evidence.");
  for (const node of data.nodes) {
    const group = svgNode("g", { tabindex: 0, role: "button", "aria-label": `${node.title}: ${node.status}` });
    group.append(svgNode("rect", { x: node.x, y: node.y, width: 205, height: 62, rx: 8, class: `dag-node ${node.status}` }));
    const title = svgNode("text", { x: node.x + 10, y: node.y + 23 }); title.textContent = node.title.slice(0, 27);
    const status = svgNode("text", { x: node.x + 10, y: node.y + 44 }); status.textContent = node.status.toUpperCase();
    group.append(title, status);
    const inspect = () => { detail.textContent = JSON.stringify({ experiment: node,
      hypothesis: result.hypothesis, measurements: result.measurements[node.parent_experiment_id ? "candidate" : "baseline"],
      evidence_ids: result.decision.evidence_ids }, null, 2); };
    group.addEventListener("click", inspect);
    group.addEventListener("keydown", event => { if (["Enter", " "].includes(event.key)) inspect(); });
    svg.append(group);
  }
  target.replaceChildren(svg, detail);
}

function renderOverview(summary, target) {
  target.replaceChildren(element("h3", "Repository overview & capabilities"));
  const total = Object.values(summary.language_bytes).reduce((a, b) => a + b, 0);
  target.append(element("p", `Composition: ${summary.composition_basis}; ${total} source bytes. Not a performance score.`));
  for (const [language, bytes] of Object.entries(summary.language_bytes)) {
    const row = element("div", "", "composition-row");
    const bar = element("span", "", "composition-bar"); bar.style.width = `${total ? bytes / total * 100 : 0}%`;
    row.append(element("span", `${language} · ${total ? (bytes / total * 100).toFixed(1) : 0}%`), bar);
    target.append(row);
  }
  for (const adapter of summary.adapters) target.append(element("p", `${adapter.adapter} · ${adapter.status.replaceAll("_", " ").toUpperCase()} — ${adapter.reason}`, "readiness"));
  const details = element("details"); details.append(element("summary", `${summary.capabilities.length} capability facts and evidence references`));
  for (const capability of summary.capabilities) details.append(element("p", `${capability.provenance.toUpperCase()} · ${capability.name} · ${capability.paths.join(", ")} · evidence ${capability.evidence_ids.join(", ")}`));
  target.append(details);
}
