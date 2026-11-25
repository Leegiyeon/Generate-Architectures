import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import test from "node:test";
import { reviewSettings, repositorySettings, repositoryURL } from "../app/pr_preview/review-link.js";

const source = readFileSync(new URL("../app/pr_preview/startup.js", import.meta.url), "utf8");
const serviceURL = "https://leegiyeon.github.io/Generate-Architectures/";
const pr = "https://github.com/2026-YOUTH-HACKATHON-TEAM28/SALGU/pull/7";

function element(extra = {}) {
  const listeners = new Map();
  return {
    hidden: false, disabled: true, textContent: "", ...extra,
    addEventListener(name, listener) { listeners.set(name, listener); },
    removeEventListener(name) { listeners.delete(name); },
    dispatch(name, event = {}) { listeners.get(name)?.(event); },
  };
}

function start(url) {
  const ids = Object.fromEntries(["startup-notice", "startup-title", "startup-message", "startup-service"]
    .map(id => [id, element()]));
  ids["startup-service"].href = serviceURL;
  const locks = Array.from({ length: 8 }, () => element());
  const forms = [element(), element(), element()];
  const modules = [];
  const window = element();
  const document = element({
    head: { append(script) { modules.push(script); } },
    getElementById(id) { return ids[id]; },
    querySelector() { return { href: serviceURL }; },
    querySelectorAll(selector) {
      if (selector === "[data-startup-lock]") return locks;
      assert.deepEqual(selector.split(",").map(value => value.trim()).sort(), ["#local-form", "#repository-form", "#review-form"]);
      return forms;
    },
    createElement() { return element(); },
  });
  vm.runInNewContext(source, { document, window, location: new URL(url), URL, URLSearchParams });
  return { ids, locks, forms, modules, document, window,
    recovery: new URL(ids["startup-service"].href) };
}

test("file startup never requests modules or allows native GET submission", () => {
  const ui = start("file:///Users/example/private-project/index.html");
  assert.equal(ui.modules.length, 0);
  assert.equal(ui.ids["startup-notice"].hidden, false);
  assert.match(ui.ids["startup-title"].textContent, /HTML 파일을 직접/);
  assert.ok(ui.locks.every(control => control.disabled));
  for (const form of ui.forms) {
    let prevented = false;
    form.dispatch("submit", { preventDefault() { prevented = true; } });
    assert.equal(prevented, true);
  }
});

test("legacy form URL recovers PR, focus and repeated scope through a fragment", () => {
  const query = new URLSearchParams({ "pr-url": pr, focus: "api", paths: " AI/chat_agent\r\nbackend/app ",
    models: "src/orm.py:Account", responses: "src/schema.py:AccountPublic", token: "never-transfer" });
  const ui = start("file:///Users/example/private-project/index.html?" + query);
  assert.equal(ui.recovery.origin + ui.recovery.pathname, serviceURL);
  assert.equal(ui.recovery.search, "");
  assert.deepEqual(reviewSettings(ui.recovery.hash), { url: pr, focus: "api",
    options: { paths: ["AI/chat_agent", "backend/app"], models: ["src/orm.py:Account"], responses: ["src/schema.py:AccountPublic"] } });
  assert.doesNotMatch(ui.recovery.href, /never-transfer|private-project|Users/);
  assert.match(ui.ids["startup-service"].textContent, /입력한 설정/);
});

test("recovery preserves known shared repository settings without unknown query data", () => {
  const settings = { url: "https://github.com/example/service", commit: "a".repeat(40), root: "src",
    file: "src/app.py", direction: "incoming", purpose: "testing" };
  const hash = new URL(repositoryURL(serviceURL, settings)).hash;
  const ui = start("file:///tmp/index.html?secret=never-transfer" + hash + "&unknown=never-transfer");
  assert.deepEqual(repositorySettings(ui.recovery.hash), settings);
  assert.doesNotMatch(ui.recovery.href, /never-transfer/);
  assert.equal(ui.modules.length, 0);
});

test("recovery drops credentials and foreign URLs, and strips GitHub URL query tokens", () => {
  for (const value of ["https://user:secret@github.com/a/b/pull/1", "https://other.example/a/b", "file:///tmp/private.py", "malformed"]) {
    assert.equal(start("file:///tmp/index.html?" + new URLSearchParams({ "pr-url": value })).recovery.href, serviceURL);
  }
  const ui = start("file:///tmp/index.html?" + new URLSearchParams({ "pr-url": pr + "?token=never-transfer#never-transfer" }));
  assert.equal(reviewSettings(ui.recovery.hash).url, pr);
  assert.doesNotMatch(ui.recovery.href, /never-transfer/);
});

test("overlong recovery never silently transfers a truncated scope", () => {
  const ui = start("file:///tmp/index.html?" + new URLSearchParams({ "pr-url": pr, paths: "a".repeat(9000) }));
  assert.equal(ui.recovery.href, serviceURL);
  assert.doesNotMatch(ui.ids["startup-service"].textContent, /입력한 설정/);
});

test("URL credentials and local absolute paths cannot pass through scope fields", () => {
  for (const value of ["file:///Users/example/private.py", "file:/Users/example/private.py",
    "https://user:password@example.invalid/private.py:Token", "/Users/example/private.py",
    "C:\\Users\\example\\private.py", "~/private.py", "data:text/plain,secret"].flatMap(value => [value, " " + value + " "])) {
    for (const field of ["paths", "models", "responses"]) {
      const ui = start("file:///tmp/index.html?" + new URLSearchParams({ "pr-url": pr, [field]: value }));
      assert.equal(ui.recovery.href, serviceURL, field + ": " + value);
    }
    for (const key of ["path", "model", "response"]) {
      assert.equal(start("file:///tmp/index.html#" + new URLSearchParams({ pr, [key]: value })).recovery.href, serviceURL);
    }
    assert.equal(start("file:///tmp/index.html#" + new URLSearchParams({ mode: "repository",
      repo: "https://github.com/example/service", commit: "a".repeat(40), root: value })).recovery.href, serviceURL);
  }
});

test("HTTP startup waits for complete app initialization before unlocking", () => {
  const ui = start(serviceURL);
  assert.equal(ui.modules.length, 1);
  assert.equal(ui.modules[0].type, "module");
  assert.equal(ui.modules[0].src, "app.js");
  assert.ok(ui.locks.every(control => control.disabled));
  ui.document.dispatch("review-ready");
  assert.equal(ui.ids["startup-notice"].hidden, true);
  assert.ok(ui.locks.every(control => !control.disabled));
  let prevented = false;
  ui.forms[0].dispatch("submit", { preventDefault() { prevented = true; } });
  assert.equal(prevented, false);
  ui.window.dispatch("error");
  assert.equal(ui.ids["startup-notice"].hidden, true);
});

test("module fetch failure and initialization exception keep controls locked with recovery", () => {
  for (const failure of [ui => ui.modules[0].dispatch("error"), ui => ui.window.dispatch("error")]) {
    const ui = start(serviceURL + "#" + new URLSearchParams({ pr, focus: "db" }));
    failure(ui);
    assert.match(ui.ids["startup-title"].textContent, /시작하지 못했습니다/);
    assert.equal(ui.ids["startup-notice"].hidden, false);
    assert.ok(ui.locks.every(control => control.disabled));
    assert.equal(reviewSettings(ui.recovery.hash).focus, "db");
  }
});
