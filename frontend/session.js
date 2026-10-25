"use strict";
(async function () {
  try {
    const response = await fetch("/api/v1/auth/status");
    if (!response.ok) throw new Error("Session status unavailable");
    const session = await response.json();
    const label = document.getElementById("session-label");
    if (label) label.textContent = session.user ? `@${session.user.login}` : session.enabled ? "Sign-in required" : "Local demo mode";
    document.getElementById("sign-in-link")?.classList.toggle("hidden", Boolean(session.user));
    document.getElementById("logout-button")?.classList.toggle("hidden", !session.user);
    document.getElementById("logout-button")?.addEventListener("click", async () => {
      const result = await fetch("/api/v1/auth/logout", { method: "POST" });
      if (!result.ok) { alert("Sign-out failed. Please retry."); return; }
      sessionStorage.removeItem("ml-analyser-live-run");
      sessionStorage.removeItem("ml-analyser-project");
      sessionStorage.removeItem("ml-analyser-library-project");
      location.assign("/login?logged_out=1");
    });
    const note = document.getElementById("provider-note");
    if (note) note.textContent = session.provider === "nebius"
      ? "Live Nemotron reasoning: Preview sends selected source excerpts to Nebius. No project code runs until you approve a compatible experiment."
      : "Offline demo reasoning: selected source files are inspected locally. No project code runs until you approve a compatible experiment.";
    const setup = document.getElementById("oauth-setup");
    if (setup) {
      setup.classList.toggle("hidden", session.configured);
      document.getElementById("github-login").classList.toggle("hidden", !session.configured);
      document.getElementById("demo-login").classList.toggle("hidden", !session.local_demo_available);
      const hosted = session.deployment_mode === "judge";
      document.getElementById("homepage-url").textContent = session.app_url;
      document.getElementById("callback-url").textContent = session.callback_url;
      document.getElementById("settings-location").textContent = hosted
        ? "Save these values in your hosting service's environment settings (Render: Environment), then redeploy."
        : "Save these values in your ignored local .env, then restart the server.";
      document.getElementById("oauth-settings").textContent = [
        `ML_ANALYSER_APP_URL=${session.app_url}`,
        "ML_ANALYSER_GITHUB_CLIENT_ID=<GitHub OAuth client ID>",
        "ML_ANALYSER_GITHUB_CLIENT_SECRET=<GitHub OAuth client secret>",
        "ML_ANALYSER_GITHUB_ALLOWED_USERS=<approved GitHub logins>",
      ].join("\n");
      document.getElementById("login-status").textContent = new URLSearchParams(location.search).has("logged_out")
        ? "You have signed out. Your saved experiments remain in your account workspace."
        : session.user ? `Already signed in as @${session.user.login}.` : session.configured ? "Use your approved GitHub account to continue." : hosted ? "Workspace sign-in is not connected yet. The experiment lab is available below." : "GitHub sign-in needs a one-time setup by the app owner.";
    }
  } catch (error) {
    const target = document.getElementById("login-status") || document.getElementById("session-label");
    if (target) target.textContent = "Cannot reach the server. Check that the app is running.";
  }
})();
