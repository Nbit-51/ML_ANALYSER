const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

async function renderSession(session) {
  const elements = new Map();
  const document = { getElementById(id) {
    if (!elements.has(id)) elements.set(id, { textContent: "", hidden: false,
      classList: { toggle(_name, value) { elements.get(id).hidden = value; } },
      addEventListener() {},
    });
    return elements.get(id);
  } };
  await vm.runInNewContext(fs.readFileSync(path.join(__dirname, "session.js"), "utf8"), {
    document, fetch: async () => ({ ok: true, json: async () => session }),
    location: { search: "" }, URLSearchParams,
  });
  return elements;
}

test("hosted OAuth setup uses the deployed origin and cannot offer local demo access", async () => {
  const elements = await renderSession({
    configured: false, enabled: false, user: null, provider: "mock", deployment_mode: "judge",
    local_demo_available: false, app_url: "https://ml-analyser.onrender.com",
    callback_url: "https://ml-analyser.onrender.com/api/v1/auth/callback",
  });
  assert.equal(elements.get("demo-login").hidden, true);
  assert.equal(elements.get("github-login").hidden, true);
  assert.match(elements.get("oauth-settings").textContent, /APP_URL=https:\/\/ml-analyser.onrender.com/);
  assert.doesNotMatch(elements.get("oauth-settings").textContent, /localhost|127\.0\.0\.1/);
  assert.match(elements.get("settings-location").textContent, /Render: Environment/);
});

test("local-only setup retains the local configuration path", async () => {
  const elements = await renderSession({
    configured: false, enabled: false, user: null, provider: "mock", deployment_mode: "local",
    local_demo_available: true, app_url: "http://127.0.0.1:8000",
    callback_url: "http://127.0.0.1:8000/api/v1/auth/callback",
  });
  assert.equal(elements.get("demo-login").hidden, false);
  assert.match(elements.get("settings-location").textContent, /local .env/);
});

test("configured sign-in hides owner setup and exposes the GitHub action", async () => {
  const elements = await renderSession({
    configured: true, enabled: true, user: null, provider: "nebius", deployment_mode: "judge",
    local_demo_available: false, app_url: "https://example.test",
    callback_url: "https://example.test/api/v1/auth/callback",
  });
  assert.equal(elements.get("oauth-setup").hidden, true);
  assert.equal(elements.get("github-login").hidden, false);
  assert.equal(elements.get("demo-login").hidden, true);
});
