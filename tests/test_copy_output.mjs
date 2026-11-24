import assert from "node:assert/strict";
import test from "node:test";
import { copyOutput } from "../app/pr_preview/copy-output.js";
import { repositoryView } from "../app/pr_preview/repository-view.js";
import { repositorySettings } from "../app/pr_preview/review-link.js";

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
    this._value = "";
    this.textContent = "";
  }
  set innerHTML(value) { throw new Error("Copy output must not interpret HTML: " + value); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  get value() { return this._value || (this.tagName === "select" ? this.children[0]?.value || "" : ""); }
  set value(value) { this._value = value; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, listener) { this.listeners[name] = listener; }
  dispatch(name) { return this.listeners[name]?.(); }
  focus() { this.document.activeElement = this; }
  select() { this.selectionStart = 0; this.selectionEnd = this.value.length; }
}

function install(t, clipboard) {
  const document = {
    createElement(tag) { return new Element(tag, this); },
    createElementNS(namespace, tag) { return this.createElement(tag); },
    createTextNode(text) { const value = this.createElement("#text"); value.textContent = text; return value; },
    activeElement: null,
  };
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

function descendants(root) { return [root, ...root.children.flatMap(descendants)]; }

function repositoryFixture() {
  const snapshot = { url: "https://github.com/example/repo", repo: "example/repo", head: "b".repeat(40),
    root: "src", totalFiles: 2, warnings: [], resolvedFrom: { branch: "main" } };
  const report = { nodes: [
    { id: "entry-id", path: "src/entry.py", detail: "직접 선언", declarations: [{ kind: "route", label: "GET /", detail: "entry", line: 2 }] },
    { id: "model-id", path: "src/모델 + #.py", detail: "직접 선언", declarations: [] },
  ], edges: [], parsed_files: 2, unreadable_paths: [], unresolved: [], warnings: [],
  omitted_nodes: 0, omitted_edges: 0, omitted_unresolved: 0 };
  return { snapshot, report };
}

const sharingOutput = section => parts(section.children.find(child => child.className === "copy-actions").children[0]);
const control = (section, id) => descendants(section).find(item => item.id === id);

test("repository sharing restores file path, direction and purpose and pins the analyzed SHA", async t => {
  const writes = [];
  install(t, { async writeText(value) { writes.push(value); } });
  const { snapshot, report } = repositoryFixture();
  const selection = { file: "src/모델 + #.py", direction: "incoming", purpose: "testing" };
  const section = repositoryView(snapshot, report, selection, "https://example.com/service/?old=discard#old");
  assert.equal(control(section, "repository-file").value, "model-id");
  assert.equal(control(section, "repository-direction").value, "incoming");
  assert.equal(control(section, "repository-purpose").value, "testing");
  const ui = sharingOutput(section);
  await ui.button.dispatch("click");
  assert.deepEqual(repositorySettings(new URL(writes[0]).hash), {
    url: snapshot.url, commit: snapshot.head, root: "src", ...selection,
  });
  assert.equal(new URL(writes[0]).pathname, "/service/");
  assert.equal(new URL(writes[0]).search, "");
  assert.match(ui.status.textContent, /고정 커밋/);
});

test("changing repository selection replaces stale share output and copies current controls", async t => {
  const writes = [];
  install(t, { async writeText(value) { writes.push(value); } });
  const { snapshot, report } = repositoryFixture();
  const section = repositoryView(snapshot, report, {}, "https://example.com/service/");
  const old = sharingOutput(section);
  old.manual.open = true;
  old.manual.dispatch("toggle");
  const file = control(section, "repository-file");
  file.value = "model-id";
  file.dispatch("change");
  const purpose = control(section, "repository-purpose");
  purpose.value = "change";
  purpose.dispatch("change");
  const direction = control(section, "repository-direction");
  direction.value = "incoming";
  direction.dispatch("change");
  const current = sharingOutput(section);
  assert.notEqual(current.root, old.root);
  assert.equal(current.text.value, "");
  assert.equal(current.status.textContent, "");
  await current.button.dispatch("click");
  assert.deepEqual(repositorySettings(new URL(writes[0]).hash), {
    url: snapshot.url, commit: snapshot.head, root: "src", file: "src/모델 + #.py", direction: "incoming", purpose: "change",
  });
});

test("unavailable shared files are disclosed and empty reports still share the pinned input", async t => {
  const writes = [];
  install(t, { async writeText(value) { writes.push(value); } });
  const { snapshot, report } = repositoryFixture();
  const requested = { file: "src/missing.py", direction: "incoming", purpose: "testing" };
  const section = repositoryView(snapshot, report, requested, "https://example.com/service/");
  assert.equal(control(section, "repository-file").value, "entry-id");
  assert.ok(descendants(section).some(item => item.textContent.includes("공유된 파일 src/missing.py") && item.textContent.includes("기본 파일로")));
  const empty = repositoryView(snapshot, { ...report, nodes: [], parsed_files: 0 }, requested, "https://example.com/service/");
  assert.ok(descendants(empty).some(item => item.textContent.includes("공유된 파일 src/missing.py")));
  await sharingOutput(empty).button.dispatch("click");
  const settings = repositorySettings(new URL(writes[0]).hash);
  assert.equal(settings.commit, snapshot.head);
  assert.equal(settings.file, "");
  assert.equal(settings.root, "src");
});
