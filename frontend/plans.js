"use strict";

function describeExecutionPlan(plan) {
  const { objective, constraints, budget } = plan.success_contract;
  const manifest = plan.manifest;
  const command = manifest.entrypoint || plan.experiment.command.join(" ");
  const changes = Object.entries(manifest.candidate_overrides).sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => `Set ${key} to ${JSON.stringify(value)} in ${manifest.config_file}`);
  const relation = objective.direction === "maximize" ? "≥" : "≤";
  const operation = objective.direction === "maximize" ? "+" : "−";
  const criteria = [
    `Candidate ${objective.metric} ${relation} baseline ${objective.metric} ${operation} ${objective.minimum_improvement}.`,
  ];
  if (objective.target !== null && objective.target !== undefined) {
    criteria.push(`Candidate ${objective.metric} ${relation} ${objective.target}.`);
  }
  const operators = { lt: "<", lte: "≤", eq: "=", gte: "≥", gt: ">" };
  for (const constraint of constraints || []) {
    criteria.push(`Guardrail: ${constraint.metric} ${operators[constraint.operator]} ${constraint.threshold}${constraint.tolerance ? ` (tolerance ${constraint.tolerance})` : ""}.`);
  }
  for (const [key, value] of Object.entries(budget || {})) {
    if (value !== null && value !== undefined) criteria.push(`Budget: ${key.replace(/^max_/, "").replaceAll("_", " ")} ≤ ${value}.`);
  }
  return {
    summary: `Run ${command} in separate baseline and candidate copies; apply the declared changes to ${manifest.config_file}.`,
    changes,
    criteria,
    verdictRule: "Accept only when the objective, guardrails and budget pass. Failed checks reject the candidate; missing or unreliable required measurements are inconclusive.",
  };
}

if (typeof module !== "undefined") module.exports = { describeExecutionPlan };
