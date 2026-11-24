import assert from "node:assert/strict";
import test from "node:test";
import { repositoryView } from "../app/pr_preview/repository-view.js";
import { repositorySettings } from "../app/pr_preview/review-link.js";

// Check rendered content and event wiring; browser layout is verified separately.
class Element {
  constructor(tag, document) {
    this.tagName = tag;
    this.document = document;
    this.children = [];
    this.attributes = {};
    this.listeners = {};
    this.textContent = "";
    this.isConnected = true;
    this.open = false;
    this._value = "";
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, listener) { this.listeners[name] = listener; }
  dispatch(name) { return this.listeners[name]?.(); }
  get value() { return this._value || (this.tagName === "select" ? this.children[0]?.value || "" : ""); }
  set value(value) { this._value = value; }
  focus() { this.document.activeElement = this; }
  scrollIntoView(options) { this.scrollOptions = options; }
}

function install(t, writes = []) {
  const document = {
    createElement(tag) { return new Element(tag, this); },
    createElementNS(namespace, tag) { return this.createElement(tag); },
    createTextNode(text) { const node = this.createElement("#text"); node.textContent = text; return node; },
  };
  for (const [name, value] of [["document", document], ["navigator", {
    clipboard: { async writeText(text) { writes.push(text); } },
  }]]) {
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, name);
    Object.defineProperty(globalThis, name, { value, configurable: true });
    t.after(() => {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else delete globalThis[name];
    });
  }
  return document;
}

const descendants = root => [root, ...root.children.flatMap(descendants)];
const content = root => descendants(root).map(node => node.textContent).join("\n");
const control = (root, id) => descendants(root).find(node => node.id === id);
const button = (root, text) => descendants(root).find(node => node.tagName === "button" && node.textContent === text);
const navigation = root => descendants(root).filter(node => node.tagName === "button" && node.textContent === "이 파일 구조 보기");
const emptyMessage = root => descendants(root).find(node => node.className === "empty")?.textContent;

function fixture() {
  const snapshot = { url: "https://github.com/example/repo", repo: "example/repo", head: "b".repeat(40),
    root: "src", totalFiles: 3, warnings: [] };
  const report = { nodes: [
    { id: "entry-id", path: "src/entry.py", detail: "직접 선언", declarations: [{ kind: "route", label: "GET /", detail: "entry", line: 2 }] },
    { id: "store-id", path: "src/모델 + #.py", detail: "직접 선언", declarations: [] },
    { id: "caller-id", path: "src/client.py", detail: "직접 선언", declarations: [] },
  ], edges: [
    { source: "entry-id", target: "store-id", label: "import store", evidence: { path: "src/entry.py", line: 4 } },
    { source: "entry-id", target: "store-id", label: "from store import Item", evidence: { path: "src/entry.py", line: 7 } },
    { source: "caller-id", target: "entry-id", label: "import entry", evidence: { path: "src/client.py", line: 9 } },
  ], parsed_files: 3, unreadable_paths: [], unresolved: [], warnings: [],
  omitted_nodes: 0, omitted_edges: 0, omitted_unresolved: 0 };
  return { snapshot, report };
}

function failedReport(reason) {
  const { snapshot, report } = fixture();
  return {
    snapshot: { ...snapshot, totalFiles: 1 },
    report: { ...report, nodes: [], edges: [], parsed_files: 0,
      unreadable_paths: ["src/entry.py"], warnings: [reason] },
  };
}

for (const [name, reason] of [
  ["HTTP source failure", "src/entry.py · GitHub 원본 조회 실패 (HTTP 429)"],
  ["Python syntax failure", "src/entry.py · Python 구문을 읽지 못함"],
]) {
  test(`an empty repository result exposes ${name} in expanded warning details`, t => {
    install(t);
    const { snapshot, report } = failedReport(reason);
    const section = repositoryView(snapshot, report, {}, "https://example.com/service/");
    const warnings = descendants(section).find(node => node.tagName === "details" && content(node).includes(reason));
    assert.ok(warnings, "the specific failure reason must remain reachable when no nodes exist");
    assert.equal(warnings.open, true);
    assert.ok(content(section).includes("src/entry.py"));
    assert.equal(navigation(section).length, 0);

    const empty = repositoryView({ ...snapshot, totalFiles: 0 }, {
      ...report, unreadable_paths: [], warnings: [],
    }, {}, "https://example.com/service/");
    assert.ok(emptyMessage(section));
    assert.ok(emptyMessage(empty));
    assert.notEqual(emptyMessage(section), emptyMessage(empty), "no Python files and failed files need different recovery guidance");
    assert.equal(descendants(empty).some(node => node.tagName === "details" && node.open), false);
  });
}

test("relationship navigation groups repeated imports without losing pinned evidence links", t => {
  install(t);
  const { snapshot, report } = fixture();
  const section = repositoryView(snapshot, report, {}, "https://example.com/service/");
  const actions = navigation(section);
  assert.equal(actions.length, 1);
  assert.equal(actions[0].attributes["aria-label"], "이 파일 구조 보기 · src/모델 + #.py");
  const links = descendants(section).find(node => node.tagName === "section"
    && node.children.some(child => child.tagName === "h3" && child.textContent === "관계의 코드 근거"));
  assert.ok(links);
  const evidence = descendants(links).filter(node => node.tagName === "a");
  for (const line of [4, 7]) {
    assert.ok(evidence.some(node => node.href === `https://github.com/example/repo/blob/${snapshot.head}/src/entry.py#L${line}`));
  }
  const body = descendants(section).find(node => node.children.some(child => child.className === "structure-viewport"));
  assert.ok(body.children.indexOf(links) > body.children.findIndex(child => child.className === "structure-viewport"));
  assert.ok(body.children.indexOf(links) < body.children.findIndex(child => child.id === "repository-review"));
});

for (const [direction, purpose, destinationId, destinationPath, purposeTitle] of [
  ["outgoing", "testing", "store-id", "src/모델 + #.py", "테스트 계획"],
  ["incoming", "change", "caller-id", "src/client.py", "변경 검토"],
]) {
  test(`${direction} navigation selects the neighbor ID and updates the plan and shared URL`, async t => {
    const writes = [];
    const document = install(t, writes);
    const { snapshot, report } = fixture();
    const section = repositoryView(snapshot, report, { direction, purpose }, "https://example.com/service/");
    const file = control(section, "repository-file");
    assert.equal(file.value, "entry-id");
    const oldPlan = control(section, "repository-review").children[0];
    const navigate = navigation(section).find(node => node.attributes["aria-label"] === `이 파일 구조 보기 · ${destinationPath}`);
    assert.ok(navigate);
    navigate.dispatch("click");

    assert.equal(file.value, destinationId);
    assert.equal(control(section, "repository-direction").value, direction);
    assert.equal(control(section, "repository-purpose").value, purpose);
    assert.equal(document.activeElement, file);
    assert.equal(file.scrollOptions?.block, "start");
    const plan = control(section, "repository-review");
    assert.notEqual(plan.children[0], oldPlan);
    assert.ok(content(plan).includes(`${destinationPath} · ${purposeTitle}`));
    await button(plan, "검토 계획 복사").dispatch("click");
    assert.ok(writes[0].includes(`선택 파일: ${destinationPath}\n`));
    assert.ok(writes[0].includes(`목적: ${purposeTitle}\n`));
    await button(section, "분석 설정 링크 복사").dispatch("click");
    assert.deepEqual(repositorySettings(new URL(writes[1]).hash), {
      url: snapshot.url, commit: snapshot.head, root: snapshot.root,
      file: destinationPath, direction, purpose,
    });
  });
}
