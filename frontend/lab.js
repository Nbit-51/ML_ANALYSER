(function (root) {
  "use strict";
  function summarizeAttempt(attempt) {
    const baseline = attempt.baseline.reference_lookups;
    const candidate = attempt.candidate.reference_lookups;
    return {
      status: attempt.decision.status,
      reduction: baseline > 0 ? (baseline - candidate) / baseline * 100 : null,
      work: `${baseline} → ${candidate}`,
      errors: attempt.candidate.incorrect_quotes,
      fields: attempt.proposal.cache_fields.map(field => ({ tenant: "Organization", sku: "Product", currency: "Currency" }[field] || field)).join(" + "),
    };
  }
  const api = { summarizeAttempt };
  if (typeof module !== "undefined") module.exports = api;
  root.LabView = api;
  if (typeof document === "undefined") return;
  const el = id => document.getElementById(id);
  const suggestionSource = provider => provider === "offline-scripted-policy" ? "Example configurations" : provider.startsWith("nebius-token-factory:") ? "AI suggestions" : provider;
  let prepared = null, capsule = null;
  const text = (tag, value, className) => {
    const node = document.createElement(tag);
    node.textContent = value;
    if (className) node.className = className;
    return node;
  };
  async function request(path, body) {
    const response = await fetch(`/api/v1/lab/${path}`, {
      method: body ? "POST" : "GET",
      headers: { "Content-Type": "application/json" },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "The request could not be completed. Please prepare a new experiment.");
    return result;
  }
  function failure(error) {
    el("lab-error").textContent = error.message;
    el("lab-error").classList.remove("hidden");
    el("lab-status").textContent = "The request stopped. See the message above for details.";
  }
  function showAttempt(attempt, target, control = false) {
    const summary = summarizeAttempt(attempt);
    target.append(text("p", control ? "REFERENCE CHECK · FIXED CONFIGURATION" : `CONFIGURATION ${attempt.number}`, "eyebrow"));
    const heading = document.createElement("div"); heading.className = "attempt-heading";
    heading.append(text("h3", summary.fields), text("span", summary.status.toUpperCase(), `verdict ${summary.status}`)); target.append(heading);
    if (control) target.append(text("p", "This fixed product-only cache checks whether the tests can detect incorrect prices. It is a reference check, separate from the suggested configurations."));
    else {
      const rationale = document.createElement("details");
      rationale.append(text("summary", "Suggestion notes"), text("p", attempt.proposal.rationale));
      target.append(rationale);
    }
    const metrics = document.createElement("div"); metrics.className = "metrics";
    for (const [label, value] of [["PRICE CALCULATIONS ↓", summary.work], ["FEWER CALCULATIONS", summary.reduction === null ? "—" : `${summary.reduction.toFixed(1)}%`], ["INCORRECT PRICES · REQUIRED: 0", String(summary.errors)]]) {
      const metric = document.createElement("div"); metric.append(text("small", label), text("strong", value)); metrics.append(metric);
    }
    target.append(metrics, text("p", `Initial checks: ${attempt.discovery.incorrect_quotes} incorrect prices. Additional test cases: ${summary.errors}.`, "muted"));
    if (attempt.counterexamples.length) {
      const detail = document.createElement("details"); detail.append(text("summary", "View incorrect results"));
      for (const example of attempt.counterexamples) detail.append(text("pre", `${JSON.stringify(example.query, null, 2)}\nExpected: ${example.expected_minor_units} minor units\nActual:   ${example.actual_minor_units} minor units`));
      target.append(detail);
    }
    if (!control) {
      const detail = document.createElement("details"); detail.append(text("summary", "Configuration changes and measurements"), text("p", attempt.decision.reason), text("pre", attempt.configuration_diff), text("pre", JSON.stringify({ paired_rounds: attempt.paired_rounds, reliability: attempt.decision.benchmark_reliability }, null, 2))); target.append(detail);
    }
  }
  function renderCapsule(report, recorded = false) {
    capsule = report;
    el("result-title").textContent = capsule.winner_attempt ? "A configuration passed all checks." : "No configuration passed every check.";
    el("evidence-mode").textContent = `${recorded ? "SAVED EXAMPLE" : "NEW MEASUREMENT"} · ${suggestionSource(capsule.plan.provider).toUpperCase()}`;
    el("result-summary").textContent = capsule.winner_attempt ? "The accepted configuration uses fewer calculations and returns the correct price for every test case." : "The experiment ended without an accepted configuration. Review the results and run details below.";
    el("stop-reason").textContent = capsule.stop_reason;
    el("result-provider").textContent = `${capsule.plan.provider} · ${capsule.model_calls} model call(s) · ${capsule.model_tokens} reported tokens · ${capsule.attempts.length} measured attempt(s)`;
    el("negative-control").replaceChildren(); showAttempt(capsule.negative_control, el("negative-control"), true);
    el("attempts").replaceChildren();
    for (const attempt of capsule.attempts) { const card = document.createElement("article"); card.className = "card attempt"; showAttempt(attempt, card); el("attempts").append(card); }
    el("limitations").replaceChildren(...capsule.limitations.map(line => text("li", line)));
    el("results").classList.remove("hidden"); el("results").scrollIntoView({ block: "start" });
  }
  el("recorded").addEventListener("click", async () => {
    try {
      const response = await fetch("/static/examples/cache-capsule-live.json");
      if (!response.ok) throw new Error("The saved result is unavailable.");
      prepared = null; el("review").classList.add("hidden");
      renderCapsule(await response.json(), true);
      el("lab-status").textContent = "Viewing a saved result. Run a new experiment to measure again.";
    } catch (error) { failure(error); }
  });
  el("prepare").addEventListener("click", async () => {
    el("prepare").disabled = true; el("recorded").disabled = true; el("lab-error").classList.add("hidden"); el("review").classList.add("hidden"); el("results").classList.add("hidden");
    el("lab-status").textContent = el("lab-mode").value === "live" ? "Getting AI configuration suggestions…" : "Preparing the example configuration…";
    try {
      prepared = await request("prepare", { mode: el("lab-mode").value });
      el("proposal-rationale").textContent = prepared.plan.first_proposal.rationale;
      el("proposal-config").textContent = prepared.plan.first_proposal.cache_fields.map(field => `${field} — ${{ tenant: "organization", sku: "product", currency: "currency" }[field] || field}`).join("\n");
      el("commitment").textContent = prepared.plan.challenge_commitment;
      el("lab-source").textContent = prepared.source;
      el("approve").disabled = false; el("review").classList.remove("hidden");
      el("lab-status").textContent = `${suggestionSource(prepared.plan.provider)} · ready for your review.`;
      el("review").scrollIntoView({ block: "start" });
    } catch (error) { failure(error); }
    finally { el("prepare").disabled = false; el("recorded").disabled = false; }
  });
  el("approve").addEventListener("click", async () => {
    if (!prepared) return;
    el("approve").disabled = true; el("prepare").disabled = true; el("recorded").disabled = true;
    el("lab-status").textContent = "Comparing configurations and checking prices. This can take a minute…";
    try {
      capsule = await request("execute", { plan: prepared.plan, approval_id: prepared.approval.id, approved: true });
      renderCapsule(capsule);
      el("lab-status").textContent = "Experiment complete. Download the report to keep a copy.";
    } catch (error) { failure(error); }
    finally { el("prepare").disabled = false; el("recorded").disabled = false; }
  });
  el("download").addEventListener("click", () => {
    if (!capsule) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(capsule, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `ml-analyser-capsule-${capsule.plan.run_id}.json`; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  request("status").then(status => {
    const live = el("lab-mode").options[1]; live.disabled = !status.live_available;
    live.textContent = status.live_available ? "AI suggestions · NVIDIA Nemotron" : "AI suggestions · not connected";
    const explainChoice = () => {
      el("provider-status").textContent = el("lab-mode").value === "live" ? "AI will suggest settings for you to review." : status.live_available ? "Start with the included cache configurations." : "AI suggestions are not connected. You can run the included configurations.";
    };
    explainChoice();
    el("lab-mode").addEventListener("change", explainChoice);
    el("provider-details").textContent = status.live_available ? `Model: ${status.model}. Daily AI experiment limit: ${status.live_daily_limit}.` : "AI suggestions require a configured model service. Saved results can be viewed without a new model request.";
  }).catch(failure);
})(typeof globalThis !== "undefined" ? globalThis : this);
