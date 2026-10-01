"use strict";

const GOALS = {
  latency: { metric: "p95_latency_ms", direction: "minimize", title: "Lower response time is better", example: "50 ms → 40 ms is an improvement of 10 ms.", detail: "P95 is the time within which 95% of successful requests finish. Compare the same workload and preserve response correctness." },
  f1: { metric: "f1", direction: "maximize", title: "Higher F1 is better", example: "0.70 → 0.80 is an improvement of 0.10.", detail: "F1 balances precision and recall on a 0–1 scale. Use the same validation data for both versions." },
  rmse: { metric: "validation_rmse", direction: "minimize", title: "Lower prediction error is better", example: "2.0 → 1.0 means smaller prediction errors.", detail: "RMSE measures how far predictions are from the correct values. Your training script must emit validation_rmse." },
  accuracy: { metric: "accuracy", direction: "maximize", title: "Higher accuracy is better", example: "0.80 → 0.90 means more correct predictions.", detail: "This preset uses a 0–1 accuracy score. For a different scale or name, choose your project's own metric." },
  throughput: { metric: "throughput_requests_per_second", direction: "maximize", title: "More requests per second is better", example: "100 → 150 requests/s is an improvement of 50 requests/s.", detail: "Keep the workload, response integrity and error limits comparable." },
};

function sourceFileAllowed(path) {
  const parts = path.toLowerCase().split("/");
  const name = parts.at(-1);
  const ignored = new Set([".git", ".aws", ".ssh", ".azure", ".venv", "venv", "node_modules", "__pycache__", "artifacts", "build", "dist", ".next", ".pytest_cache", ".mypy_cache", ".ruff_cache"]);
  return !parts.some(part => ignored.has(part)) && !name.startsWith(".env") &&
    !/secret|credential/.test(name) && !["id_rsa", "id_ed25519", ".npmrc", ".pypirc", ".netrc"].includes(name) &&
    !/\.(pem|key|p12|pfx|pyc|db|log)$/.test(name);
}

function selectSourceFiles(files) {
  const kept = Array.from(files).filter(file => sourceFileAllowed(file.webkitRelativePath));
  if (!kept.length) throw new Error("No source files selected after excluding credentials and generated files.");
  if (kept.length > 1000 || kept.some(file => file.size > 2 * 1024 * 1024) || kept.reduce((n, file) => n + file.size, 0) > 20 * 1024 * 1024) {
    throw new Error("Select a smaller source folder: limit 1,000 files, 2 MB per file and 20 MB total.");
  }
  return kept;
}

if (typeof module !== "undefined") module.exports = { GOALS, sourceFileAllowed, selectSourceFiles };

if (typeof document !== "undefined") {
  const byId = id => document.getElementById(id);
  let chosen = [];
  const invalidate = () => {
    byId("analysis-output").classList.add("hidden");
    byId("plan-review").classList.add("hidden");
    prepared = null;
  };
  function switchMode(mode) {
    for (const name of ["repo", "demo"]) {
      byId(`${name}-tab`).setAttribute("aria-selected", String(name === mode));
      byId(name === "repo" ? "repository-panel" : "demo-panel").classList.toggle("hidden", name !== mode);
    }
  }
  byId("repo-tab").addEventListener("click", () => switchMode("repo"));
  byId("demo-tab").addEventListener("click", () => switchMode("demo"));
  if (new URLSearchParams(location.search).get("mode") === "demo") switchMode("demo");
  function updateGoal() {
    invalidate();
    const goal = GOALS[byId("goal-preset").value];
    byId("custom-goal").classList.toggle("hidden", Boolean(goal));
    if (goal) {
      byId("analysis-metric").value = goal.metric;
      byId("analysis-direction").value = goal.direction;
      byId("goal-explanation").textContent = `${goal.title}. ${goal.example} ${goal.detail} Metric: ${goal.metric}.`;
    } else {
      byId("analysis-metric").value = "";
      byId("analysis-direction").value = "";
      byId("goal-explanation").textContent = "Tell us what your metric means. The evaluator will use your direction; it will not guess from the name.";
    }
    byId("analysis-target").value = "";
    byId("analysis-improvement").value = "";
  }
  byId("goal-preset").addEventListener("change", updateGoal);
  byId("analysis-path").addEventListener("input", invalidate);
  updateGoal();
  const fail = message => { byId("import-error").textContent = message; byId("import-error").classList.remove("hidden"); };
  async function importFiles(kind, payload, label) {
    byId("import-error").classList.add("hidden");
    byId("import-status").textContent = "Importing source files…";
    byId("github-import-button").disabled = byId("folder-import-button").disabled = true;
    try {
      const response = await fetch(`/api/v1/repositories/${kind}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const data = await response.json();
      if (response.status === 401) { location.assign("/login"); return; }
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Import could not be completed. Check the file limits.");
      invalidate();
      byId("analysis-path").value = data.project_path;
      byId("import-status").textContent = `${label} · ${data.files} files ready for preview. ${data.skipped ? `${data.skipped} excluded.` : ""} Original unchanged.`;
    } catch (error) { fail(error.message); byId("import-status").textContent = "Import not completed. Your previous selection is unchanged."; }
    finally { byId("github-import-button").disabled = byId("folder-import-button").disabled = false; }
  }
  byId("github-import-form").addEventListener("submit", event => {
    event.preventDefault();
    const url = byId("github-url").value.trim();
    importFiles("github", { url }, url);
  });
  byId("folder-picker").addEventListener("change", event => {
    chosen = [];
    byId("folder-import-button").classList.add("hidden");
    byId("import-error").classList.add("hidden");
    try {
      chosen = selectSourceFiles(event.target.files);
      byId("folder-summary").textContent = `${chosen[0].webkitRelativePath.split("/")[0]} · ${chosen.length} source files selected; ${event.target.files.length - chosen.length} excluded. A copy will be uploaded to this app.`;
      byId("folder-import-button").classList.remove("hidden");
    } catch (error) { fail(error.message); }
  });
  byId("folder-import-button").addEventListener("click", async () => {
    byId("folder-import-button").disabled = true;
    try {
      const files = [];
      for (const file of chosen) {
        const content = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result).split(",")[1]);
          reader.onerror = () => reject(new Error("Could not read selected file."));
          reader.readAsDataURL(file);
        });
        files.push({ path: file.webkitRelativePath.split("/").slice(1).join("/"), content });
      }
      await importFiles("folder", { files }, chosen[0].webkitRelativePath.split("/")[0]);
    } catch (error) { fail(error.message); }
    finally { byId("folder-import-button").disabled = false; }
  });
}
