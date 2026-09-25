"use strict";

function describeMetric(metric) {
  const name = metric.toLowerCase();
  if (name === "f1" || name.endsWith("_f1")) {
    return "F1 balances precision and recall. It ranges from 0 to 1; higher is usually better.";
  }
  if (name.includes("precision")) {
    return "Precision is the share of positive predictions that were correct. Higher is usually better.";
  }
  if (name.includes("recall")) {
    return "Recall is the share of actual positives the model found. Higher is usually better.";
  }
  if (name.includes("accuracy")) {
    return "Accuracy is the share of predictions that were correct. Check class balance before relying on it alone.";
  }
  if (name.includes("max_abs")) {
    return "Maximum absolute difference is the largest output gap from a reference. Smaller means closer numerical agreement.";
  }
  if (name.includes("p95") && name.includes("latency")) {
    return "P95 latency is the time at or below which 95% of measured requests finished. Lower is better.";
  }
  if (name.includes("p50") && (name.includes("latency") || name.endsWith("_ms"))) {
    return "P50 is the median time: half of measured runs finished at or below this value. Lower is better.";
  }
  if (name.includes("latency") || name.endsWith("_ms")) {
    return "Latency is time per operation, usually in milliseconds. Lower is better for the same workload.";
  }
  if (name.includes("throughput")) {
    return "Throughput is work completed per second. Higher is better when correctness stays the same.";
  }
  if (name.includes("error_rate")) {
    return "Error rate is the share of failed requests or predictions. Lower is better.";
  }
  if (name.includes("rmse")) {
    return "RMSE summarizes prediction error and penalizes large misses. Lower is better.";
  }
  if (name.includes("loss")) {
    return "Loss is the model's optimization score. Lower is usually better, but compare on the same evaluation data.";
  }
  return "This is a project-defined metric. Check its definition and compare values only under the same evaluation method.";
}

function formatMetricValue(value, metric) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  const absolute = Math.abs(value);
  const number = absolute > 0 && absolute < 0.001 ? value.toExponential(2) : value.toFixed(4);
  return metric.toLowerCase().endsWith("_ms") || metric.toLowerCase().includes("latency")
    ? `${number} ms`
    : number;
}

function metricPreference(metric) {
  const name = metric.toLowerCase();
  if (name === "f1" || name.endsWith("_f1") || name.includes("precision") ||
      name.includes("recall") || name.includes("accuracy") || name.includes("throughput")) {
    return "maximize";
  }
  if (name.includes("latency") || name.endsWith("_ms") || name.includes("error_rate") ||
      name.includes("max_abs") || name.includes("rmse") || name.includes("loss")) {
    return "minimize";
  }
  return null;
}

function interpretMetricChange(baseline, candidate, metric, direction = metricPreference(metric)) {
  if (!Number.isFinite(baseline) || !Number.isFinite(candidate)) return "No comparable measurement.";
  if (candidate === baseline) return "Unchanged from baseline.";
  const movement = candidate > baseline ? "higher" : "lower";
  if (!direction) return `Candidate is ${movement}; check this project's metric definition to judge it.`;
  const favorable = (direction === "maximize" && candidate > baseline) ||
    (direction === "minimize" && candidate < baseline);
  return `Candidate is ${movement} than baseline; that is ${favorable ? "favorable" : "unfavorable"} for this metric. Check the full decision for targets and guardrails.`;
}

function interpretRecordedValue(value, metric, objective, constraints) {
  if (!Number.isFinite(value)) return "This prior value is not a usable number.";
  if (metric === objective.metric && Number.isFinite(objective.target)) {
    const meets = objective.direction === "minimize"
      ? value <= objective.target : value >= objective.target;
    return `Against your ${formatMetricValue(objective.target, metric)} target, this prior value ${meets ? "meets" : "misses"} the target. Re-measure under comparable conditions before deciding whether a new change helped.`;
  }
  const guardrail = constraints.find((item) => item.metric === metric);
  if (guardrail) {
    const meets = guardrail.operator === "lte" ? value <= guardrail.threshold
      : guardrail.operator === "gte" ? value >= guardrail.threshold
      : value === guardrail.threshold;
    return `Against your ${guardrail.operator === "lte" ? "at-most" : guardrail.operator === "gte" ? "at-least" : "equal-to"} ${formatMetricValue(guardrail.threshold, metric)} guardrail, this prior value ${meets ? "is within the limit" : "is outside the limit"}. This is not a fresh safety check.`;
  }
  return "This is a prior recorded value, not a new measurement or evidence of improvement.";
}
