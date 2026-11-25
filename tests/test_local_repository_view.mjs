import assert from "node:assert/strict";
import test from "node:test";
import { repositoryView } from "../app/pr_preview/repository-view.js";
import { repositoryReview, repositoryReviewText } from "../app/pr_preview/repository-review.js";
import { repositoryProposals, repositoryProposalText } from "../app/pr_preview/repository-proposals.js";
import { localCodeContext } from "../app/pr_preview/repository-source.js";

// Exercise the result's rendering/event contract without reading private source through a browser or server.
class Element {
  constructor(tag, document) {
    this.tagName = tag; this.document = document; this.children = []; this.attributes = {};
    this.listeners = {}; this.textContent = ""; this.isConnected = true; this.open = false; this._value = "";
  }
  set innerHTML(value) { throw new Error("Local source must use textContent"); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; }
  addEventListener(name, listener) { this.listeners[name] = listener; }
  dispatch(name) { return this.listeners[name]?.(); }
  get value() { return this._value || (this.tagName === "select" ? this.children[0]?.value || "" : ""); }
  set value(value) { this._value = value; }
  focus() { this.document.activeElement = this; }
  select() {}
  scrollIntoView(options) { this.scrollOptions = options; }
  cloneNode() {
    const copy = new Element(this.tagName, this.document);
    copy.textContent = this.textContent; copy.attributes = { ...this.attributes };
    copy.children = this.children.map(child => child.cloneNode(true));
    return copy;
  }
  querySelectorAll(tag) { return descendants(this).filter(item => item !== this && item.tagName === tag); }
  click() { this.document.downloads.push({ filename: this.download, href: this.href }); }
}

const descendants = root => [root, ...root.children.flatMap(descendants)];
const content = root => descendants(root).map(item => item.textContent).join("\n");
const control = (root, id) => descendants(root).find(item => item.id === id);
const button = (root, label) => descendants(root).find(item => item.tagName === "button" && item.textContent === label);
const noLinks = root => assert.equal(descendants(root).some(item => item.tagName === "a" || item.href || item.attributes.href), false);

function install(t) {
  const writes = [], blobs = [], serialized = [];
  const document = { downloads: [],
    createElement(tag) { return new Element(tag, this); },
    createElementNS(namespace, tag) { return this.createElement(tag); },
    createTextNode(text) { const value = this.createElement("#text"); value.textContent = text; return value; },
  };
  const forbidden = () => { throw new Error("Local result must not use URLs, network, or browser storage"); };
  for (const [name, value] of [["document", document], ["navigator", { clipboard: { async writeText(text) { writes.push(text); } } }],
    ["window", new Proxy({}, { get: forbidden })], ["localStorage", new Proxy({}, { get: forbidden })],
    ["sessionStorage", new Proxy({}, { get: forbidden })], ["fetch", forbidden],
    ["XMLSerializer", class { serializeToString(svg) { serialized.push(svg); return content(svg); } }],
    ["setTimeout", callback => { callback(); return 0; }]]) {
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, name);
    Object.defineProperty(globalThis, name, { value, configurable: true });
    t.after(() => descriptor ? Object.defineProperty(globalThis, name, descriptor) : delete globalThis[name]);
  }
  for (const [name, value] of [["createObjectURL", blob => { blobs.push(blob); return "blob:local-export"; }], ["revokeObjectURL", () => {}]]) {
    const descriptor = Object.getOwnPropertyDescriptor(URL, name);
    Object.defineProperty(URL, name, { value, configurable: true });
    t.after(() => descriptor ? Object.defineProperty(URL, name, descriptor) : delete URL[name]);
  }
  return { document, writes, blobs, serialized };
}

function fixture() {
  const files = [
    { path: "src/private + #.py", after: ["# first", "from .models import Item", "# context before", "@app.get('/private')",
      "# <script>alert('private')</script>", "class Item(Base):", "# context after", "# beyond excerpt"].join("\n"), warnings: [] },
    { path: "src/models.py", after: "# model\nfrom .private import Item\n# last", warnings: [] },
  ];
  const snapshot = { source: "local", kind: "repository", repo: "비공개 프로젝트", head: "", root: "src", files,
    knownPaths: files.map(item => item.path), totalFiles: 2, fetchedAt: "2026-11-25T04:05:06.000Z", warnings: [] };
  const report = { nodes: [
    { id: "entry", path: files[0].path, detail: "Python 파일", line: 1, declarations: [
      { kind: "route", line: 4, label: "GET /private", detail: "직접 라우트" },
      { kind: "model", line: 6, label: "Item", detail: "직접 테이블" } ] },
    { id: "model", path: files[1].path, detail: "Python 파일", line: 1, declarations: [] },
  ], edges: [
    { source: "entry", target: "model", label: "from .models import Item", evidence: { path: files[0].path, line: 2 } },
    { source: "model", target: "entry", label: "from .private import Item", evidence: { path: files[1].path, line: 2 } },
  ], parsed_files: 2, unreadable_paths: [], unresolved: [], warnings: [], omitted_nodes: 0, omitted_edges: 0, omitted_unresolved: 0 };
  return { snapshot, report };
}

test("local results use selected-time identity with no GitHub or share URLs", t => {
  install(t);
  const { snapshot, report } = fixture();
  const view = repositoryView(snapshot, report);
  assert.match(content(view), /로컬 폴더 현재 코드 구조/);
  assert.ok(content(view).includes(snapshot.fetchedAt));
  assert.match(content(view), /이전 상태와의 변경 비교는 포함하지 않습니다/);
  assert.match(content(view), /SVG에는 파일명·선언 정보가 포함/);
  assert.doesNotMatch(content(view), /커밋|공개 저장소|github\.com|분석 설정 링크/);
  noLinks(view);
  for (const svg of descendants(view).filter(item => item.tagName === "svg" && item.attributes.xmlns)) {
    const metadata = descendants(svg).find(item => item.tagName === "metadata");
    assert.equal(JSON.parse(metadata.textContent).source, "local");
    assert.equal(JSON.parse(metadata.textContent).selectedAt, snapshot.fetchedAt);
    assert.equal(Object.hasOwn(JSON.parse(metadata.textContent), "commit"), false);
  }
});

test("local evidence uses numbered native details and treats script strings as literal source", t => {
  install(t);
  const { snapshot, report } = fixture();
  const view = repositoryView(snapshot, report);
  const source = descendants(view).find(item => item.className === "local-source"
    && item.children.some(child => child.tagName === "summary" && child.textContent.startsWith("GET /private")));
  assert.ok(source);
  assert.match(content(source), /1–7행 발췌/);
  const pre = descendants(source).find(item => item.tagName === "pre");
  assert.equal(pre.className, "local-source-code");
  assert.match(pre.textContent, /> 4 \| @app\.get/);
  assert.ok(pre.textContent.includes("  5 | # <script>alert('private')</script>"));
  assert.equal(pre.children.length, 0);
  assert.equal(descendants(view).some(item => item.tagName === "script"), false);
  assert.equal(pre.textContent.includes("beyond excerpt"), false);
  assert.deepEqual(localCodeContext(snapshot, "src/models.py", 3), { start: 1, end: 3,
    text: "  1 | # model\n  2 | from .private import Item\n> 3 | # last" });
});

test("missing files, unreadable sources, and invalid evidence rows stay unconfirmed", t => {
  install(t);
  const { snapshot, report } = fixture();
  snapshot.files.push({ path: "unreadable.py", after: null });
  for (const [path, line] of [["missing.py", 1], ["unreadable.py", 1], ["src/models.py", 0],
    ["src/models.py", -1], ["src/models.py", 999], ["src/models.py", "2"], ["src/models.py", 1.5]]) {
    assert.equal(localCodeContext(snapshot, path, line), null);
    report.unresolved.push({ path, line, label: "import unknown", reason: "미확인" });
  }
  const view = repositoryView(snapshot, report);
  const unknown = descendants(view).filter(item => item.className === "local-source" && content(item).includes("코드 근거 미확인"));
  assert.equal(unknown.length, 7);
  noLinks(view);
});

test("local copied plans and proposal text keep relative evidence and selection time", async t => {
  const { writes } = install(t);
  const { snapshot, report } = fixture();
  for (const purpose of ["onboarding", "change", "testing"]) {
    const view = repositoryView(snapshot, report, { purpose });
    await button(view, "검토 계획 복사").dispatch("click");
    const text = writes.at(-1);
    assert.ok(text.includes(`로컬 폴더: ${snapshot.repo}`));
    assert.ok(text.includes(`선택 시각: ${snapshot.fetchedAt}`));
    assert.ok(text.includes("src/private + #.py:4"));
    assert.doesNotMatch(text, /커밋|공개 저장소|https?:\/\//);
  }
  const result = repositoryProposals(report, "entry");
  for (const candidate of result.candidates) {
    const text = repositoryProposalText(snapshot, result, candidate.id);
    assert.ok(text.includes(snapshot.fetchedAt));
    assert.match(text, /로컬 코드: src\/private \+ #\.py:/);
    assert.doesNotMatch(text, /커밋|https?:\/\//);
  }
  const review = repositoryReview(report, "entry");
  review.steps[0].evidence.push({ path: "absent.py", line: 77, label: "unavailable" });
  assert.match(repositoryReviewText(snapshot, review), /로컬 코드 근거 미확인: absent\.py:77/);
});

test("local file, direction, purpose, and improvement selections remain interactive", async t => {
  const { writes, document } = install(t);
  const { snapshot, report } = fixture();
  const view = repositoryView(snapshot, report, { direction: "incoming", purpose: "change" });
  const proposals = control(view, "repository-proposal");
  assert.equal(proposals.children.length, 2);
  proposals.value = "break-cycle";
  proposals.dispatch("change");
  assert.match(content(control(view, "repository-proposals")), /순환/);
  const purpose = control(view, "repository-purpose");
  purpose.value = "testing";
  purpose.dispatch("change");
  const navigate = button(view, "이 파일 구조 보기");
  navigate.dispatch("click");
  const file = control(view, "repository-file");
  assert.equal(file.value, "model");
  assert.equal(document.activeElement, file);
  assert.equal(control(view, "repository-direction").value, "incoming");
  assert.equal(purpose.value, "testing");
  await button(view, "검토 계획 복사").dispatch("click");
  assert.match(writes[0], /선택 파일: src\/models\.py\n목적: 테스트 계획/);
  control(view, "repository-direction").value = "outgoing";
  control(view, "repository-direction").dispatch("change");
  file.value = "entry"; file.dispatch("change");
  assert.equal(control(view, "repository-file").value, "entry");
  assert.ok(descendants(view).some(item => item.tagName === "textarea" && item.readOnly && item.value.includes(snapshot.fetchedAt)));
  noLinks(view);
});

test("local SVG exports identify current snapshots without fake commits or external file links", async t => {
  const { document, blobs, serialized } = install(t);
  const { snapshot, report } = fixture();
  const view = repositoryView(snapshot, report);
  button(view, "선택 구조 SVG 저장").dispatch("click");
  button(view, "구조 비교 SVG 저장").dispatch("click");
  assert.deepEqual(document.downloads.map(item => item.filename), ["repository-local-outgoing.svg", "proposal-local-separate-roles.svg"]);
  assert.equal(blobs.length, 2);
  for (const [index, blob] of blobs.entries()) {
    assert.equal(blob.type, "image/svg+xml;charset=utf-8");
    assert.ok((await blob.text()).includes(snapshot.fetchedAt));
    assert.doesNotMatch(await blob.text(), /커밋|github\.com|"commit"/);
    noLinks(serialized[index]);
  }
});

test("empty local results preserve recovery guidance and never add sharing", t => {
  install(t);
  const { snapshot, report } = fixture();
  const empty = { ...report, nodes: [], edges: [], parsed_files: 0 };
  for (const totalFiles of [0, 1]) {
    const view = repositoryView({ ...snapshot, totalFiles }, empty);
    assert.match(content(view), totalFiles === 0 ? /분석 가능한 일반 Python 파일이 없습니다/ : /표시할 Python 파일이 없습니다/);
    assert.ok(content(view).includes(snapshot.fetchedAt));
    assert.doesNotMatch(content(view), /커밋|분석 설정 링크/);
    assert.equal(button(view, "선택 구조 SVG 저장"), undefined);
    noLinks(view);
  }
});
