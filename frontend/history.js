"use strict";

function reportRowSummary(report) {
  const verdict = {accepted:"Accepted", rejected:"Rejected", inconclusive:"Inconclusive"}[report.decision] || "Unknown decision";
  return `${report.project_id} · ${report.metric} · ${verdict}`;
}
if (typeof module !== "undefined") module.exports = { reportRowSummary };

if (typeof document !== "undefined") {
  const historyNode = document.getElementById("report-history");
  const statusNode = document.getElementById("history-status");
  let displayedReport = null;
  document.addEventListener("workbench-result", event => { displayedReport = event.detail; });
  document.getElementById("download-report").addEventListener("click", () => {
    if (!displayedReport) return;
    const blob = new Blob([JSON.stringify(displayedReport, null, 2)], {type:"application/json"});
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = `ml-analyser-${displayedReport.run_id.replace(/[^a-z0-9_-]/gi, "")}.json`;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  });
  async function openReport(runId, button) {
    button.disabled = true;
    try {
      const result = await api(`/${encodeURIComponent(runId)}/report`);
      if (pollTimer) clearTimeout(pollTimer);
      prepared = null;
      document.getElementById("plan-review").classList.add("hidden");
      document.getElementById("run-id").textContent = runId.slice(0,8);
      renderTimeline(result.state_history);
      renderResult(result);
      setStatus("idle", "Saved report · no new experiment executed");
      document.getElementById("results").scrollIntoView({behavior:"smooth",block:"start"});
    } catch (error) { statusNode.textContent = error.message; }
    finally { button.disabled = false; }
  }
  async function refreshReports() {
    const refresh = document.getElementById("refresh-reports"); refresh.disabled = true;
    try {
      const reports = await api("/history");
      historyNode.replaceChildren();
      statusNode.textContent = reports.length ? "Latest measured reports from this workspace. Opening one does not execute project code." : "No saved reports yet. Complete a supported experiment to see it here.";
      for (const report of reports) {
        const row = document.createElement("article"); row.className = "saved-report-row";
        const info = document.createElement("div");
        const title = document.createElement("strong"); title.textContent = reportRowSummary(report);
        const detail = document.createElement("small"); detail.textContent = `${report.adapter} · ${new Date(report.observed_at).toLocaleString()} · ${report.run_id.slice(0,8)}`;
        info.append(title,detail);
        const button = document.createElement("button"); button.type = "button"; button.className = "secondary-button";
        button.textContent = "Open report"; button.addEventListener("click", () => openReport(report.run_id,button));
        row.append(info,button); historyNode.append(row);
      }
    } catch (error) { statusNode.textContent = error.message; }
    finally { refresh.disabled = false; }
  }
  document.getElementById("refresh-reports").addEventListener("click", refreshReports);
  document.addEventListener("workbench-run-completed", refreshReports);
  refreshReports();
}
