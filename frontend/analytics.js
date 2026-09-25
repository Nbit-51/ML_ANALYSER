"use strict";

// Pure transformations: no adapter names, DOM access or inferred metric semantics.
function comparisonData(result) {
  if (result.comparisons) return result.comparisons;
  const left = new Map((result.measurements?.baseline || []).map(m => [m.metric, m]));
  const right = new Map((result.measurements?.candidate || []).map(m => [m.metric, m]));
  return [...new Set([...left.keys(), ...right.keys()])].sort().map(name => {
    const a = left.get(name), b = right.get(name), metadata = b || a;
    const comparable = a && b && a.unit === b.unit;
    const delta = comparable ? b.value - a.value : null;
    return { name, label: metadata.label || name, unit: metadata.unit,
      direction: result.success_contract?.objective.metric === name
        ? result.success_contract.objective.direction : metadata.direction || null,
      baseline: a?.value ?? null, candidate: b?.value ?? null, delta,
      percentage_delta: delta !== null && a.value !== 0 ? delta / Math.abs(a.value) * 100 : null,
      evidence_ids: [...new Set([...(a?.evidence_ids || []), ...(b?.evidence_ids || [])])],
      raw_samples_exist: Boolean(a?.raw_samples?.length || b?.raw_samples?.length) };
  });
}

function chartScale(values) {
  const finite = values.filter(Number.isFinite);
  const min = Math.min(0, ...finite), max = Math.max(0, ...finite);
  const span = max - min || 1;
  return { min, max, position: value => 8 + ((value - min) / span) * 284 };
}

function distributionData(baseline = [], candidate = [], bins = 12) {
  const all = [...baseline, ...candidate].filter(Number.isFinite);
  if (!all.length) return null;
  const min = Math.min(...all), max = Math.max(...all), span = max - min || 1;
  const histogram = samples => {
    const counts = Array(bins).fill(0);
    for (const value of samples.filter(Number.isFinite)) {
      counts[Math.min(bins - 1, Math.floor((value - min) / span * bins))]++;
    }
    return counts;
  };
  return { min, max, baseline: histogram(baseline), candidate: histogram(candidate) };
}

function guardrailData(result) {
  const metrics = comparisonData(result);
  const objective = result.success_contract?.objective;
  const rows = (result.success_contract?.constraints || []).map(rule => {
    const measured = metrics.find(m => m.name === rule.metric);
    const evaluation = result.decision?.constraints?.find(c => c.metric === rule.metric);
    return { ...rule, baseline: measured?.baseline, candidate: measured?.candidate,
      status: evaluation ? (evaluation.passed ? "pass" : "fail") : "inconclusive" };
  });
  if (objective) {
    const metric = metrics.find(m => m.name === objective.metric);
    const evaluated = result.decision?.objective;
    rows.unshift({ metric: objective.metric, operator: objective.direction,
      threshold: objective.target ?? "No target", minimum_improvement: objective.minimum_improvement,
      baseline: metric?.baseline, candidate: metric?.candidate,
      status: evaluated ? (evaluated.passed ? "pass" : "fail") : "inconclusive" });
  }
  return rows;
}

function lineageData(experiments = []) {
  const byId = new Map(experiments.map(e => [e.id, e]));
  const depth = (item, visited = new Set()) => {
    if (!item.parent_experiment_id || !byId.has(item.parent_experiment_id)) return 0;
    if (visited.has(item.id)) throw new Error("Experiment lineage contains a cycle");
    visited.add(item.id);
    return 1 + depth(byId.get(item.parent_experiment_id), visited);
  };
  const columns = new Map();
  const nodes = experiments.map(item => {
    const level = depth(item), row = columns.get(level) || 0;
    columns.set(level, row + 1);
    return { ...item, x: 20 + level * 235, y: 20 + row * 90 };
  });
  return { nodes, edges: nodes.filter(n => byId.has(n.parent_experiment_id))
    .map(n => ({ from: n.parent_experiment_id, to: n.id })) };
}

function reliabilityData(result) {
  const reliability = result.benchmark_reliability || result.decision?.benchmark_reliability;
  return { status: reliability?.status || "not_assessed", reasons: reliability?.reasons || [],
    environment: reliability?.environment_compatible === true ? "Compatible"
      : reliability?.environment_compatible === false ? "Mismatch" : "Not assessed",
    rows: Object.entries(result.measurements || {}).flatMap(([variant, values]) =>
      values.filter(m => m.raw_samples?.length || m.failed_sample_count).map(m => ({
        variant, metric: m.metric, samples: m.raw_samples.length,
        warmup: m.warmup_count, failed: m.failed_sample_count,
        cv: m.summary?.coefficient_of_variation ?? null,
        comparison_samples: m.reliability_samples?.length || m.raw_samples.length,
        comparison_cv: sampleVariation(m.reliability_samples?.length ? m.reliability_samples : m.raw_samples),
        fingerprint: m.environment_fingerprint })) ) };
}

function sampleVariation(samples) {
  if (!samples.length) return null;
  const mean = samples.reduce((a, b) => a + b, 0) / samples.length;
  if (!mean) return null;
  const variance = samples.length > 1 ? samples.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (samples.length - 1) : 0;
  return Math.sqrt(variance) / Math.abs(mean);
}

function unitValue(value, unit) {
  return Number.isFinite(value) ? `${Number(value.toPrecision(6))}${unit ? ` ${unit}` : ""}` : "—";
}

if (typeof module !== "undefined") module.exports = {
  comparisonData, chartScale, distributionData, guardrailData, lineageData, reliabilityData, unitValue,
};
