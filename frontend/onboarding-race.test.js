const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}
const flush = () => new Promise(resolve => setImmediate(resolve));

function loadOnboarding() {
  const elements = new Map();
  const events = new Map();
  function element() {
    const classes = new Set();
    return {
      value: "", textContent: "", options: [], children: [], listeners: new Map(),
      classList: {
        add(name) { classes.add(name); }, remove(name) { classes.delete(name); },
        contains(name) { return classes.has(name); },
        toggle(name, hidden) { if (hidden) classes.add(name); else classes.delete(name); },
      },
      append(...items) { this.children.push(...items); this.options.push(...items.flatMap(item => item.options.length ? item.options : [item])); },
      replaceChildren(...items) { this.children = []; this.options = []; this.append(...items); },
      setAttribute() {}, addEventListener(name, listener) { this.listeners.set(name, listener); },
    };
  }
  const document = {
    getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
    createElement() { return element(); },
    addEventListener(name, listener) { events.set(name, listener); },
  };
  document.getElementById("goal-preset").options = [{ value:"f1", textContent:"F1" }];
  document.getElementById("goal-preset").value = "f1";
  const storage = new Map([["ml-analyser-library-project", "imported"], ["ml-analyser-project", "imported/evaluation"]]);
  const requests = [];
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "onboarding.js"), "utf8"), {
    document, prepared: null, URLSearchParams, location:{search:""},
    sessionStorage:{getItem:key => storage.get(key),setItem:(key,value) => storage.set(key,value),removeItem:key => storage.delete(key)},
    fetch(url) { const pending = deferred(); requests.push({url, ...pending}); return pending.promise; },
  });
  return {
    document, requests,
    showResult() {
      document.getElementById("results").classList.remove("hidden");
      events.get("workbench-result")({detail:{run_id:"saved"}});
    },
    respond(index, data) { requests[index].resolve({ok:true,json:async () => data}); },
  };
}

test("opening a saved result wins over a delayed initial project-list response", async () => {
  const page = loadOnboarding();
  page.showResult();
  page.respond(0, [{project_path:"imported",display_name:"Repo",origin:"github"}]);
  await flush();
  assert.equal(page.requests.length, 1, "project restoration must not invalidate the opened report");
  assert.equal(page.document.getElementById("results").classList.contains("hidden"), false);
});

test("opening a saved result cancels pending root discovery and nested auto-selection", async () => {
  const page = loadOnboarding();
  page.respond(0, [{project_path:"imported",display_name:"Repo",origin:"github"}]);
  await flush();
  assert.match(page.requests[1].url, /project_path=imported$/);
  page.showResult();
  page.respond(1, {adapters:[],benchmark_projects:[{project_path:"imported/evaluation",display_name:"evaluation"}]});
  await flush();
  assert.equal(page.requests.length, 2, "stale restoration must not request the nested evaluation");
  assert.equal(page.document.getElementById("results").classList.contains("hidden"), false);
  assert.equal(page.document.getElementById("benchmark-project").options.length, 0);
  page.document.getElementById("saved-project").listeners.get("change")({target:{value:"other"}});
  assert.equal(page.document.getElementById("results").classList.contains("hidden"), true,
    "an intentional new project selection still clears the old result");
});
