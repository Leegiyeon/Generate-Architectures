import assert from "node:assert/strict";
import test from "node:test";
import { copyOutput } from "../app/pr_preview/copy-output.js";
import { repositoryView } from "../app/pr_preview/repository-view.js";

// The component needs only DOM construction, events and text selection. No browser
// implementation is emulated: layout, native details behavior and clipboard
// permissions are verified in the live browser separately.
class Element {
  constructor(tag, document) {
    this.tagName = tag;
    this.document = document;
    this.children = [];
    this.attributes = {};
    this.listeners = {};
    this.isConnected = true;
    this.open = false;
    this.disabled = false;
    this.value = "";
    this.textContent = "";
  }
  set innerHTML(value) { throw new Error("Copy output must not interpret HTML: " + value); }
  append(...children) { this.children.push(...children); }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, listener) { this.listeners[name] = listener; }
  dispatch(name) { return this.listeners[name]?.(); }
  focus() { this.document.activeElement = this; }
  select() { this.selectionStart = 0; this.selectionEnd = this.value.length; }
}

function install(t, clipboard) {
  const document = { createElement(tag) { return new Element(tag, this); }, activeElement: null };
  for (const [key, value] of [["document", document], ["navigator", { clipboard }]]) {
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, key);
    Object.defineProperty(globalThis, key, { value, configurable: true });
    t.after(() => {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else delete globalThis[key];
    });
  }
  return document;
}

function parts(root) {
  const [actions, status, manual] = root.children;
  return { root, button: actions.children[0], status, manual, summary: manual.children[0], text: manual.children[1].children[0] };
}

function output(getText = () => "fixed commit\nhttps://github.com/example/repo/blob/" + "a".repeat(40)) {
  return parts(copyOutput({ label: "요약 복사", getText, successMessage: "복사했습니다.", fallbackLabel: "복사할 요약" }));
}

test("denied clipboard exposes and selects the exact read-only payload beside its action", async t => {
  const document = install(t, { async writeText() { throw new Error("NotAllowedError"); } });
  const payload = '<script>alert("plain text")</script>\n커밋: ' + "a".repeat(40) + "\n근거: https://github.com/a/b/blob/abc/file.py#L12";
  const ui = output(() => payload);
  await ui.button.dispatch("click");
  assert.equal(ui.manual.open, true);
  assert.equal(ui.text.value, payload);
  assert.equal(ui.text.readOnly, true);
  assert.equal(document.activeElement, ui.text);
  assert.equal(ui.text.selectionEnd, payload.length);
  assert.match(ui.status.textContent, /자동 복사가 허용되지 않아/);
  assert.equal(ui.status.attributes.role, "status");
  assert.equal(ui.button.disabled, false);
});

test("missing Clipboard API still leaves the complete payload usable", async t => {
  install(t, undefined);
  const ui = output(() => "https://example.com/#pr=exact&path=a%2Fb");
  await ui.button.dispatch("click");
  assert.equal(ui.manual.open, true);
  assert.equal(ui.text.value, "https://example.com/#pr=exact&path=a%2Fb");
  assert.equal(ui.button.disabled, false);
});

test("manual output is available before any copy attempt and refreshes on reopening", t => {
  install(t, undefined);
  let value = "first scope";
  const ui = output(() => value);
  assert.equal(ui.summary.textContent, "복사할 요약 보기");
  assert.equal(ui.text.value, "");
  ui.manual.open = true;
  ui.manual.dispatch("toggle");
  assert.equal(ui.text.value, "first scope");
  ui.manual.open = false;
  ui.manual.dispatch("toggle");
  value = "second scope";
  ui.manual.open = true;
  ui.manual.dispatch("toggle");
  assert.equal(ui.text.value, "second scope");
});

test("successful copy reports locally, clears an old fallback and blocks duplicate pending requests", async t => {
  let complete;
  const writes = [];
  install(t, { writeText(value) { writes.push(value); return new Promise(resolve => { complete = resolve; }); } });
  const ui = output(() => "actual snapshot");
  ui.manual.open = true;
  ui.text.value = "old snapshot";
  const pending = ui.button.dispatch("click");
  assert.equal(ui.button.disabled, true);
  assert.equal(ui.manual.open, false);
  assert.equal(ui.text.value, "");
  await ui.button.dispatch("click");
  assert.deepEqual(writes, ["actual snapshot"]);
  complete();
  await pending;
  assert.equal(ui.status.textContent, "복사했습니다.");
  assert.equal(ui.button.disabled, false);
});

test("payload preparation failures do not write, expose stale output or claim success", async t => {
  let writes = 0;
  install(t, { async writeText() { writes++; } });
  const ui = output(() => { throw new Error("공유 링크가 너무 깁니다."); });
  ui.text.value = "stale scope";
  await ui.button.dispatch("click");
  assert.equal(writes, 0);
  assert.equal(ui.text.value, "");
  assert.equal(ui.manual.open, false);
  assert.equal(ui.status.textContent, "공유 링크가 너무 깁니다.");
  assert.equal(ui.button.disabled, false);
  ui.manual.open = true;
  ui.manual.dispatch("toggle");
  assert.equal(ui.manual.open, false);
  assert.equal(ui.status.textContent, "공유 링크가 너무 깁니다.");
});

test("a removed output cannot take focus or overwrite a replacement after clipboard rejection", async t => {
  let reject;
  const document = install(t, { writeText() { return new Promise((resolve, fail) => { reject = fail; }); } });
  const first = output(() => "old analysis");
  const pending = first.button.dispatch("click");
  const replacement = output(() => "new analysis");
  replacement.text.focus();
  first.root.isConnected = false;
  reject(new Error("denied"));
  await pending;
  assert.equal(first.manual.open, false);
  assert.equal(first.status.textContent, "");
  assert.equal(replacement.status.textContent, "");
  assert.equal(document.activeElement, replacement.text);
});

test("repository latest-origin heading keeps the exact pinned SHA and branch as plain text", t => {
  install(t, undefined);
  const sha = "a".repeat(40);
  const snapshot = { repo: "example/repo", head: sha, root: ".", totalFiles: 0, warnings: [], resolvedFrom: { branch: "feature/<latest>" } };
  const report = { parsed_files: 0, nodes: [], unreadable_paths: [] };
  const section = repositoryView(snapshot, report);
  const heading = section.children[0];
  assert.match(heading.children[1].textContent, new RegExp(sha));
  assert.match(heading.children[2].textContent, /기본 브랜치 feature\/<latest>의 최신 커밋을 위 SHA로 고정/);
  const explicit = repositoryView({ ...snapshot, resolvedFrom: undefined }, report);
  assert.equal(explicit.children[0].children.length, 2);
});
