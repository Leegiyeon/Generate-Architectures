import test from "node:test";
import assert from "node:assert/strict";
import { componentSource, structureSuggestions } from "../app/pr_preview/architecture.js";
import { evidenceLocation } from "../app/pr_preview/evidence.js";

test("structure sources use each snapshot's commit and previous filename", () => {
  const pull = { baseRepo: "base/repo", headRepo: "fork/repo", base: "a".repeat(40), head: "b".repeat(40),
    files: [{ path: "app/new name.py", previous_path: "app/old.py" }] };
  const component = { path: "app/new name.py", line: 7 };
  assert.equal(componentSource(pull, component, "before"), `https://github.com/base/repo/blob/${pull.base}/app/old.py#L7`);
  assert.equal(componentSource(pull, component, "after"), `https://github.com/fork/repo/blob/${pull.head}/app/new%20name.py#L7`);
});

function report(before, after, models = [], migrations = []) {
  return { structure: { before: { nodes: before }, after: { nodes: after } }, models, migrations };
}

test("review suggestions require observed changed declarations", () => {
  const route = { kind: "route", status: "unchanged" };
  const unchanged = structureSuggestions(report([route], [route]));
  assert.equal(unchanged.length, 1);
  assert.match(unchanged[0].reason, /도출/);
  const changed = structureSuggestions(report([], [{ ...route, status: "added", label: 'GET /items' }]));
  assert.equal(changed[0].title, "API 계약 테스트를 함께 확인하세요");
  assert.match(changed[0].reason, /GET \/items/);
  const removed = structureSuggestions(report([{ ...route, status: "removed" }], []));
  assert.equal(removed[0].title, changed[0].title);
});

test("coexisting route and DB declarations preserve unknown access relationships", () => {
  const output = structureSuggestions(report([], [{ kind: "route", status: "modified" }, { kind: "model", status: "unchanged" }]));
  assert.equal(output.length, 2);
  assert.match(output[1].reason, /호출·데이터 접근 관계는 분석하지 않았습니다/);
  assert.equal(output.some(item => item.title.includes("DB 변경과 배포")), false);
});

test("a migration-only change yields a review action without claiming DB safety", () => {
  const output = structureSuggestions(report([], [], [], ["선언 추가 · 컬럼 변경 user.email"]));
  assert.equal(output.length, 1);
  assert.match(output[0].title, /DB 변경/);
  assert.match(output[0].action, /실제 DB의 호환성을 판정할 수는 없습니다/);
});

test("source-like text inside field values remains text without creating a fake link", () => {
  const entry = `  필드 선언값 · Item.note · 지정 없음 → Field(description=' · fake.py:99')`;
  assert.equal(evidenceLocation(entry, [{ path: 'fake.py' }]), null);
  const main = `선언 추가 · 컬럼 변경 user.note (타입 선언 · make_type(' · fake.py:99')) · real.py:3`;
  const location = evidenceLocation(main, [{ path: 'real.py' }]);
  assert.equal(location.path, 'real.py');
  assert.equal(location.line, 3);
  assert.equal(main.slice(0, location.start), `선언 추가 · 컬럼 변경 user.note (타입 선언 · make_type(' · fake.py:99'))`);
  assert.equal(evidenceLocation('변경 · other.py:7', [{ path: 'real.py' }]), null);
});

test("source locations preserve previous snapshots and trailing comparison notes", () => {
  const files = [{ path: 'app/routes.py' }];
  const previous = evidenceLocation('삭제 · GET /items · app/routes.py:4 (이전 커밋)', files);
  assert.equal(previous.previous, true);
  assert.equal(previous.line, 4);
  const duplicate = evidenceLocation('선언 수정 · GET /items · app/routes.py:8 · 동일 경로의 등록 2 → 3건', files);
  assert.equal(duplicate.line, 8);
  assert.equal(duplicate.previous, false);
});
