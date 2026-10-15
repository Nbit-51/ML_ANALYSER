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

function declaredGoals(adapters) {
  return adapters.filter(adapter => ["supported_and_executable", "preview_only"].includes(adapter.status))
    .flatMap(adapter => (adapter.measurement_definitions || []).map(definition => ({
      metric: definition.name, direction: definition.direction || null, unit: definition.unit || null,
      label: definition.label || definition.name.replaceAll("_", " "), adapter: adapter.adapter,
    })));
}

function readinessMessage(adapters) {
  if (adapters.some(adapter => adapter.status === "supported_and_executable")) {
    return "Ready to prepare a declared experiment. Preview first, review the plan, then approve it.";
  }
  if (adapters.some(adapter => adapter.status === "preview_only")) {
    return "Ready for preview. A benchmark is declared, but this host cannot execute it; check its runtime requirements.";
  }
  return "Ready for preview. To measure a change, add a benchmark manifest that declares the command, metrics and candidate configuration.";
}

if (typeof module !== "undefined") module.exports = { GOALS, sourceFileAllowed, selectSourceFiles, declaredGoals, readinessMessage };

if (typeof document !== "undefined") {
  const byId = id => document.getElementById(id);
  let chosen = [];
  let projectGoals = [];
  let selectionVersion = 0;
  const presetOptions = Array.from(byId("goal-preset").options).map(option => ({value:option.value, text:option.textContent}));
  const invalidate = () => {
    byId("analysis-output").classList.add("hidden");
    byId("plan-review").classList.add("hidden");
    byId("results").classList.add("hidden");
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
    const value = byId("goal-preset").value;
    const declaration = value.startsWith("declared-") ? projectGoals[Number(value.slice(9))] : null;
    const goal = declaration || GOALS[value];
    byId("custom-goal").classList.toggle("hidden", Boolean(goal?.direction));
    byId("analysis-metric").readOnly = Boolean(declaration);
    if (goal) {
      byId("analysis-metric").value = goal.metric;
      byId("analysis-direction").value = goal.direction || "";
      byId("goal-explanation").textContent = declaration
        ? `${goal.label} is declared by ${goal.adapter}${goal.unit ? ` in ${goal.unit}` : ""}. ${goal.direction === "minimize" ? "A smaller value counts as improvement." : goal.direction === "maximize" ? "A larger value counts as improvement." : "The manifest does not define improvement direction. Choose it below."} This is a metric definition, not a measured value.`
        : `${goal.title}. ${goal.example} ${goal.detail} Metric: ${goal.metric}.`;
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
  byId("analysis-form").addEventListener("input", invalidate);
  byId("analysis-form").addEventListener("change", invalidate);
  updateGoal();
  const fail = message => { byId("import-error").textContent = message; byId("import-error").classList.remove("hidden"); };
  async function repositoryApi(path, options) {
    const response = await fetch(`/api/v1/repositories${path}`, options);
    const data = await response.json();
    if (response.status === 401) { location.assign("/login"); throw new Error("Sign in to continue."); }
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Could not load the project.");
    return data;
  }
  function renderGoals(adapters) {
    projectGoals = declaredGoals(adapters);
    const select = byId("goal-preset");
    select.replaceChildren();
    if (projectGoals.length) {
      const group = document.createElement("optgroup");
      group.label = "Declared by this project";
      projectGoals.forEach((goal, index) => {
        const option = document.createElement("option");
        option.value = `declared-${index}`;
        option.textContent = `${goal.label}${goal.unit ? ` (${goal.unit})` : ""} · ${goal.adapter}`;
        group.append(option);
      });
      select.append(group);
    }
    const group = document.createElement("optgroup"); group.label = "Other goals for preview";
    for (const {value, text} of presetOptions) {
      const option = document.createElement("option"); option.value = value; option.textContent = text;
      group.append(option);
    }
    select.append(group);
    updateGoal();
  }
  async function inspectProject(path) {
    const version = ++selectionVersion;
    invalidate();
    byId("analysis-path").value = path;
    byId("project-readiness").classList.add("hidden");
    // Clear old declarations immediately; a failed load must not reuse another project's metrics.
    renderGoals([]);
    if (!path) { sessionStorage.removeItem("ml-analyser-project"); return; }
    sessionStorage.setItem("ml-analyser-project", path);
    byId("import-status").textContent = "Reading declared benchmark settings…";
    try {
      const data = await repositoryApi(`/details?project_path=${encodeURIComponent(path)}`);
      if (version !== selectionVersion) return;
      renderGoals(data.adapters);
      const box = byId("project-readiness");
      box.replaceChildren(); box.classList.remove("hidden");
      const message = document.createElement("p"); message.className = "goal-explanation";
      message.textContent = readinessMessage(data.adapters); box.append(message);
      const more = document.createElement("details");
      const title = document.createElement("summary"); title.textContent = "Benchmark requirements";
      more.append(title);
      for (const adapter of data.adapters) {
        const line = document.createElement("p"); line.className = "help-text";
        line.textContent = `${adapter.adapter}: ${adapter.reason}`; more.append(line);
      }
      box.append(more);
      byId("import-status").textContent = "Project selected. Choose a goal below, then preview the repository.";
    } catch (error) { if (version === selectionVersion) { fail(error.message); byId("import-status").textContent = "Project details unavailable. Check the selected folder."; } }
  }
  async function refreshProjects(selectPath = null) {
    byId("refresh-projects").disabled = true;
    try {
      const projects = await repositoryApi("");
      const select = byId("saved-project"); select.replaceChildren();
      const placeholder = document.createElement("option"); placeholder.value = ""; placeholder.textContent = "Choose a project…"; select.append(placeholder);
      for (const project of projects) {
        const option = document.createElement("option"); option.value = project.project_path;
        option.textContent = `${project.display_name} · ${project.origin}${project.imported_at ? ` · ${new Date(project.imported_at).toLocaleDateString()}` : ""}`;
        select.append(option);
      }
      byId("library-status").textContent = projects.length ? `${projects.length} projects in your workspace. Select one to continue.` : "No saved projects yet. Import a repository below.";
      const previous = selectPath || byId("analysis-path").value || sessionStorage.getItem("ml-analyser-project");
      if (projects.some(project => project.project_path === previous)) {
        select.value = previous;
        if (selectPath || !byId("analysis-path").value) await inspectProject(previous);
        byId("new-project-options").open = false;
      }
    } catch (error) { byId("library-status").textContent = error.message; }
    finally { byId("refresh-projects").disabled = false; }
  }
  byId("saved-project").addEventListener("change", event => {
    byId("import-error").classList.add("hidden");
    inspectProject(event.target.value);
    byId("new-project-options").open = !event.target.value;
  });
  byId("refresh-projects").addEventListener("click", () => refreshProjects());
  byId("analysis-path").addEventListener("change", event => inspectProject(event.target.value.trim()));
  refreshProjects();
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
      await refreshProjects(data.project_path);
      byId("import-status").textContent = `${data.display_name || label} · ${data.files} files ready for preview. ${data.skipped ? `${data.skipped} excluded.` : ""} Original unchanged.`;
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
      const selection = chosen.slice();
      const files = [];
      for (const file of selection) {
        const content = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result).split(",")[1]);
          reader.onerror = () => reject(new Error("Could not read selected file."));
          reader.readAsDataURL(file);
        });
        files.push({ path: file.webkitRelativePath.split("/").slice(1).join("/"), content });
      }
      const display_name = selection[0].webkitRelativePath.split("/")[0].slice(0,120);
      await importFiles("folder", { files, display_name }, display_name);
    } catch (error) { fail(error.message); }
    finally { byId("folder-import-button").disabled = false; }
  });
}
