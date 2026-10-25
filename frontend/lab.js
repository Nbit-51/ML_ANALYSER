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
      fields: attempt.proposal.cache_fields.join(" + "),
    };
  }
  const api = { summarizeAttempt };
  if (typeof module !== "undefined") module.exports = api;
  root.LabView = api;
  if (typeof document === "undefined") return;
  const el = id => document.getElementById(id);
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
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "The request could not be completed. Prepare a new campaign.");
    return result;
  }
  function failure(error) {
    el("lab-error").textContent = error.message;
    el("lab-error").classList.remove("hidden");
    el("lab-status").textContent = "Stopped. No unmeasured improvement is claimed.";
  }
  function showAttempt(attempt, target, control = false) {
    const summary = summarizeAttempt(attempt);
    target.append(text("p", control ? "DECLARED NEGATIVE CONTROL · NOT A MODEL PROPOSAL" : `AGENT ATTEMPT ${attempt.number}`, "eyebrow"));
    const heading = document.createElement("div"); heading.className = "attempt-heading";
    heading.append(text("h3", summary.fields), text("span", summary.status.toUpperCase(), `verdict ${summary.status}`)); target.append(heading);
    if (control) target.append(text("p", "A product-only cache passes the narrow discovery set, but returns the wrong prices under the challenge. This control checks that the verifier can detect the intended failure."));
    else {
      const rationale = document.createElement("details");
      rationale.append(text("summary", "Why this configuration was proposed"), text("p", attempt.proposal.rationale));
      target.append(rationale);
    }
    const metrics = document.createElement("div"); metrics.className = "metrics";
    for (const [label, value] of [["REFERENCE LOOKUPS ↓", summary.work], ["WORK REDUCTION", summary.reduction === null ? "—" : `${summary.reduction.toFixed(1)}%`], ["INCORRECT PRICES · MUST BE 0", String(summary.errors)]]) {
      const metric = document.createElement("div"); metric.append(text("small", label), text("strong", value)); metrics.append(metric);
    }
    target.append(metrics, text("p", `Discovery: ${attempt.discovery.incorrect_quotes} incorrect quotes. Fresh challenge: ${summary.errors}. ${attempt.decision.reason}`, "muted"));
    if (attempt.counterexamples.length) {
      const detail = document.createElement("details"); detail.append(text("summary", "Inspect concrete counterexamples"));
      for (const example of attempt.counterexamples) detail.append(text("pre", `${JSON.stringify(example.query, null, 2)}\nExpected: ${example.expected_minor_units} minor units\nActual:   ${example.actual_minor_units} minor units`));
      target.append(detail);
    }
    if (!control) {
      const detail = document.createElement("details"); detail.append(text("summary", "Configuration diff and repeated measurements"), text("pre", attempt.configuration_diff), text("pre", JSON.stringify({ paired_rounds: attempt.paired_rounds, reliability: attempt.decision.benchmark_reliability }, null, 2))); target.append(detail);
    }
  }
  function renderCapsule(report, recorded = false) {
    capsule = report;
    el("result-title").textContent = capsule.winner_attempt ? "An improvement that survived the challenge." : "The evidence blocked this campaign.";
    el("evidence-mode").textContent = recorded ? "RECORDED LIVE RUN · NO NEW INFERENCE OR MEASUREMENT" : "MEASURED IN THIS CAMPAIGN";
    el("result-summary").textContent = capsule.stop_reason;
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
      if (!response.ok) throw new Error("Recorded evidence is unavailable.");
      prepared = null; el("review").classList.add("hidden");
      renderCapsule(await response.json(), true);
      el("lab-status").textContent = "Inspecting recorded live evidence. No new experiment or model request ran.";
    } catch (error) { failure(error); }
  });
  el("prepare").addEventListener("click", async () => {
    el("prepare").disabled = true; el("recorded").disabled = true; el("lab-error").classList.add("hidden"); el("review").classList.add("hidden"); el("results").classList.add("hidden");
    el("lab-status").textContent = el("lab-mode").value === "live" ? "Nemotron is reading the source and proposing a bounded configuration…" : "Preparing the offline policy…";
    try {
      prepared = await request("prepare", { mode: el("lab-mode").value });
      el("proposal-rationale").textContent = prepared.plan.first_proposal.rationale;
      el("proposal-config").textContent = JSON.stringify(prepared.plan.first_proposal.cache_fields, null, 2);
      el("commitment").textContent = prepared.plan.challenge_commitment;
      el("lab-source").textContent = prepared.source;
      el("approve").disabled = false; el("review").classList.remove("hidden");
      el("lab-status").textContent = `Prepared · ${prepared.plan.provider} · waiting for approval.`;
      el("review").scrollIntoView({ block: "start" });
    } catch (error) { failure(error); }
    finally { el("prepare").disabled = false; el("recorded").disabled = false; }
  });
  el("approve").addEventListener("click", async () => {
    if (!prepared) return;
    el("approve").disabled = true; el("prepare").disabled = true; el("recorded").disabled = true;
    el("lab-status").textContent = "Running controlled measurements. Rejected candidates may trigger a Nemotron revision; this can take a minute…";
    try {
      capsule = await request("execute", { plan: prepared.plan, approval_id: prepared.approval.id, approved: true });
      renderCapsule(capsule);
      el("lab-status").textContent = "Completed. Download the evidence before the free host restarts.";
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
    live.textContent = status.live_available ? `${status.model} · Nebius Token Factory` : "Live Nebius inference is unavailable";
    el("provider-status").textContent = status.live_available ? `Live inference is optional and capped at ${status.live_daily_limit} campaigns per UTC day on this instance. Offline mode uses no model credits.` : "Offline mode remains fully measurable and replayable. The host has not enabled live inference.";
  }).catch(failure);
})(typeof globalThis !== "undefined" ? globalThis : this);
