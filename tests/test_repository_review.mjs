import assert from "node:assert/strict";
import test from "node:test";
import { repositoryReview, repositoryReviewText } from "../app/pr_preview/repository-review.js";

const file = (path, declarations = []) => ({ id: path, path, line: 1, declarations, omitted_declarations: 0 });
const edge = (source, target, line) => ({ source, target, label: `import ${target}`, evidence: { path: source, line } });
const route = (line = 8) => ({ kind: "route", line, label: "GET /items" });
const model = (line = 20) => ({ kind: "model", line, label: "Item" });
const report = () => ({ nodes: [file("app/routes.py", [route()]), file("app/models.py", [model()]), file("app/main.py")],
  edges: [edge("app/routes.py", "app/models.py", 3), edge("app/main.py", "app/routes.py", 4)],
  parsed_files: 3, unresolved: [], unreadable_paths: [], warnings: [], omitted_nodes: 0, omitted_edges: 0, omitted_unresolved: 0 });

test("purpose changes the plan using the same selected file and observed evidence", () => {
  const data = report();
  const onboarding = repositoryReview(data, "app/routes.py");
  const change = repositoryReview(data, "app/routes.py", "change");
  const testing = repositoryReview(data, "app/routes.py", "testing");
  assert.deepEqual(onboarding.steps.map(item => item.id), ["declarations", "imports"]);
  assert.deepEqual(change.steps.map(item => item.id), ["consumers", "declarations"]);
  assert.deepEqual(testing.steps.map(item => item.id), ["route-tests", "imports"]);
  assert.equal(change.steps[0].evidence[0].path, "app/main.py");
  assert.equal(change.steps[0].evidence[0].line, 4);
  assert.equal(testing.steps[0].evidence[0].line, 8);
  assert.notEqual(onboarding.steps[0].action, change.steps[1].action);
});

test("file counts deduplicate neighbors without losing import relation counts", () => {
  const data = report();
  data.edges.push(edge("app/main.py", "app/routes.py", 9), edge("app/routes.py", "app/models.py", 10));
  const change = repositoryReview(data, "app/routes.py", "change");
  assert.equal(change.coverage.incoming_files, 1);
  assert.match(change.steps[0].observation, /파일 1개.*직접 import 관계 2개/);
  assert.equal(change.steps[0].evidence.length, 2);
  const onboarding = repositoryReview(data, "app/routes.py");
  assert.equal(onboarding.coverage.outgoing_files, 1);
  assert.match(onboarding.steps[1].observation, /직접 import 관계 2개.*파일 1개/);
});

test("multiple import aliases on one source line count relations without claiming separate statements", () => {
  const data = report();
  data.edges = [edge("app/routes.py", "app/models.py", 3), edge("app/routes.py", "app/main.py", 3)];
  const item = repositoryReview(data, "app/routes.py").steps[1];
  assert.match(item.observation, /직접 import 관계 2개.*파일 2개/);
  assert.doesNotMatch(item.observation, /import 선언 2개/);
  assert.equal(item.evidence.length, 1);
  assert.equal(item.evidence[0].line, 3);
  assert.equal(item.omitted_evidence, 0);
});

test("evidence is deduplicated by location and capped with an exact omitted count", () => {
  const data = report();
  data.edges = Array.from({ length: 9 }, (_, index) => edge("app/main.py", "app/routes.py", index + 1));
  data.edges.push(edge("app/main.py", "app/routes.py", 1));
  const item = repositoryReview(data, "app/routes.py", "change").steps[0];
  assert.equal(item.evidence.length, 6);
  assert.equal(item.omitted_evidence, 3);
  assert.deepEqual(item.evidence.map(value => value.line), [1, 2, 3, 4, 5, 6]);
});

test("declarations belong to the selected file, and route and model candidates remain separate", () => {
  const data = report();
  assert.deepEqual(repositoryReview(data, "app/models.py", "testing").steps.map(item => item.id), ["model-tests", "imports"]);
  data.nodes[0].declarations.push(model(30));
  const review = repositoryReview(data, "app/routes.py", "testing");
  assert.deepEqual(review.steps.map(item => item.id), ["route-tests", "model-tests", "imports"]);
  assert.deepEqual(review.steps[1].evidence, [{ path: "app/routes.py", line: 30, label: "Item" }]);
  assert.match(review.steps[1].action, /실제 DB/);
});

test("missing graph connections do not become claims of safety or absence of tests", () => {
  const data = report();
  data.edges = [];
  const change = repositoryReview(data, "app/main.py", "change");
  assert.match(change.steps[0].action, /변경 영향이 없다고 판단하지/);
  assert.match(change.steps[1].action, /원본의 함수·클래스와 실제 사용 지점/);
  assert.match(change.steps[1].action, /선언 생략 안내/);
  const onboarding = repositoryReview(data, "app/main.py");
  assert.match(onboarding.steps[0].action, /원본의 함수·클래스와 사용 지점/);
  assert.match(onboarding.steps[0].action, /역할이 없다고 판단하지/);
  const testing = repositoryReview(data, "app/main.py", "testing");
  assert.deepEqual(testing.steps.map(item => item.id), ["test-scope", "imports"]);
  assert.match(testing.steps[0].action, /기존 테스트의 유무.*판정하지/);
  assert.deepEqual(testing.steps[0].evidence, [{ path: "app/main.py", line: 1, label: "app/main.py" }]);
  assert.match(testing.steps[1].action, /독립적인 파일이라고 판단하지/);
});

test("text export states the exact number of omitted evidence locations", () => {
  const data = report();
  data.nodes[0].declarations = Array.from({ length: 8 }, (_, index) => route(index + 1));
  const review = repositoryReview(data, "app/routes.py");
  assert.equal(review.steps[0].omitted_evidence, 2);
  const snapshot = { repo: "example/demo", head: "c".repeat(40), root: ".", totalFiles: 3, warnings: [] };
  assert.match(repositoryReviewText(snapshot, review), /이 항목의 근거 2개는 목록 한도로 생략/);
});

test("incomplete analysis remains explicit and per-file unknown counts stay scoped", () => {
  const data = report();
  Object.assign(data, { omitted_nodes: 2, omitted_edges: 11, omitted_unresolved: 4,
    unreadable_paths: ["broken.py"], warnings: ["route prefix unknown"],
    unresolved: [{ path: "app/routes.py", line: 1 }, { path: "app/models.py", line: 2 }] });
  data.nodes[0].omitted_declarations = 5;
  const review = repositoryReview(data, "app/routes.py");
  assert.equal(review.coverage.selected_unresolved, 1);
  const limits = review.limits.join("\n");
  assert.match(limits, /파일 2개·관계 11개/);
  assert.match(limits, /직접 선언 5개/);
  assert.match(limits, /해석하지 못한 파일 1개/);
  assert.match(limits, /표시된 항목은 1건/);
  assert.match(limits, /전체 미확인 import 목록에서 4건/);
  assert.match(limits, /추가 확인 안내 1건/);
});

test("invalid purpose defaults safely and missing selection produces no fabricated plan", () => {
  assert.equal(repositoryReview(report(), "app/routes.py", "__proto__").purpose, "onboarding");
  const missing = repositoryReview(report(), "not-found.py", "testing");
  assert.equal(missing.selected_path, null);
  assert.deepEqual(missing.steps, []);
  assert.match(missing.summary, /찾을 수 없습니다/);
});

test("text export pins every evidence URL and carries scope, omissions and loader warnings", () => {
  const data = report();
  data.nodes[0].omitted_declarations = 2;
  const snapshot = { repo: "example/demo", head: "a".repeat(40), root: "backend", totalFiles: 8,
    warnings: ["Python 원본 100개 한도"] };
  const review = repositoryReview(data, "app/routes.py", "change");
  const text = repositoryReviewText(snapshot, review);
  assert.ok(text.includes(snapshot.head));
  assert.match(text, /Python 소스 루트: backend/);
  assert.match(text, /목적: 변경 검토/);
  assert.match(text, /원본 8개 중 구문 분석 3개, 그래프 파일 3개·관계 2개/);
  assert.match(text, new RegExp(`https://github.com/example/demo/blob/${snapshot.head}/app/main.py#L4`));
  assert.match(text, /직접 선언 2개가 생략/);
  assert.match(text, /Python 원본 100개 한도/);
  assert.match(text, /실제 실행 영향.*확인하지 않았습니다/);
});

test("export preserves unusual source names as text and URL-encodes their evidence path", () => {
  const path = "app/odd [name]<file>.py";
  const data = { ...report(), nodes: [file(path, [{ ...route(), label: "GET /[x]<raw>\nnext" }])], edges: [] };
  const snapshot = { repo: "example/demo", head: "b".repeat(40), root: ".", totalFiles: 1, warnings: [] };
  const text = repositoryReviewText(snapshot, repositoryReview(data, path));
  assert.match(text, /근거: GET \/\[x\]<raw> next/);
  assert.ok(text.includes(`/app/odd%20%5Bname%5D%3Cfile%3E.py#L8`));
  assert.ok(!text.includes("[GET"));
});
