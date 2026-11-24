import assert from "node:assert/strict";
import test from "node:test";
import { repositoryProposals, repositoryProposalText } from "../app/pr_preview/repository-proposals.js";

const file = (path, declarations = []) => ({ id: path, path, line: 1, detail: "Python 파일", declarations, omitted_declarations: 0 });
const edge = (source, target, line = 2) => ({ source, target, label: `import ${target}`, evidence: { path: source, line } });
const route = line => ({ kind: "route", line, label: `GET /items${line}` });
const model = line => ({ kind: "model", line, label: `Item${line}` });
const report = (nodes = [file("main.py")], edges = []) => ({ nodes, edges,
  parsed_files: nodes.length, unresolved: [], unreadable_paths: [], warnings: [],
  omitted_nodes: 0, omitted_edges: 0, omitted_unresolved: 0 });
const snapshot = { repo: "example/demo", head: "a".repeat(40), root: "backend", totalFiles: 3, warnings: [] };

test("a file without either observed rule does not receive an invented proposal or safety verdict", () => {
  const result = repositoryProposals(report(), "main.py");
  assert.deepEqual(result.candidates, []);
  assert.match(result.empty_reason, /안전.*판정은 아닙니다/);
  assert.match(result.limits.join("\n"), /아직 적용·실행·검증하지 않은/);
  assert.equal(repositoryProposals(report(), "missing.py").selected_path, null);
});

test("role split requires both observed declaration kinds on the selected file", () => {
  const data = report([file("routes.py", [route(8)]), file("models.py", [model(20)])]);
  assert.deepEqual(repositoryProposals(data, "routes.py").candidates, []);
  data.nodes[0].declarations.push(model(30));
  const before = JSON.stringify(data);
  const candidate = repositoryProposals(data, "routes.py").candidates[0];
  assert.equal(candidate.id, "separate-roles");
  assert.equal(candidate.before.nodes.length, 1);
  assert.deepEqual(candidate.before.edges, []);
  assert.equal(candidate.after.nodes.length, 2);
  assert.ok(candidate.after.nodes.every(item => item.proposed && !Object.hasOwn(item, "path")));
  assert.ok(candidate.after.edges.every(item => item.proposed));
  assert.deepEqual(candidate.evidence.map(item => item.line), [8, 30]);
  assert.match(candidate.assumptions.join("\n"), /실제.*사용.*확정하지/);
  assert.match(candidate.tradeoffs.join("\n"), /작은 예제/);
  assert.equal(JSON.stringify(data), before);
  assert.deepEqual(repositoryProposals(data, "models.py").candidates, []);
});

test("role evidence cap keeps a table source even when many routes appear first", () => {
  const data = report([file("main.py", [...Array.from({ length: 9 }, (_, index) => route(index + 10)), model(50)])]);
  const candidate = repositoryProposals(data, "main.py").candidates[0];
  assert.equal(candidate.evidence.length, 6);
  assert.equal(candidate.omitted_evidence, 4);
  assert.deepEqual(candidate.evidence.slice(0, 2).map(item => item.line), [10, 50]);
  data.nodes[0].declarations.push(model(50));
  assert.equal(repositoryProposals(data, "main.py").candidates[0].omitted_evidence, 4);
});

test("a two-file cycle preserves observed direction and conditionally removes the selected outgoing pair", () => {
  const data = report([file("a.py"), file("b.py")], [edge("a.py", "b.py", 3), edge("b.py", "a.py", 4)]);
  const candidate = repositoryProposals(data, "a.py").candidates[0];
  assert.equal(candidate.id, "break-cycle");
  assert.deepEqual(candidate.before.edges.map(item => [item.source, item.target]), [["a.py", "b.py"], ["b.py", "a.py"]]);
  assert.deepEqual(candidate.after.edges.map(item => [item.source, item.target]), [["b.py", "a.py"]]);
  assert.deepEqual(candidate.changes.map(item => [item.status, item.source, item.target]), [["remove", "a.py", "b.py"]]);
  assert.ok(candidate.after.nodes.every(item => !item.proposed && item.path === item.id));
  assert.match(candidate.assumptions.join("\n"), /전체 순환이 해결/);
  assert.match(candidate.actions.join("\n"), /단순 import 삭제로 대체하지/);
  assert.equal(repositoryProposals(data, "b.py").candidates[0].changes[0].source, "b.py");
});

test("the shortest cycle wins over an earlier longer path and ties are stable across report order", () => {
  const nodes = [file("root.py"), file("a.py"), file("b.py"), file("c.py"), file("z.py")];
  const edges = [edge("root.py", "a.py"), edge("a.py", "b.py"), edge("b.py", "root.py"),
    edge("root.py", "z.py"), edge("z.py", "root.py"), edge("root.py", "c.py"), edge("c.py", "root.py")];
  const candidate = repositoryProposals(report(nodes, edges), "root.py").candidates[0];
  assert.deepEqual(candidate.before.nodes.map(item => item.id), ["root.py", "c.py"]);
  const reversed = repositoryProposals(report([...nodes].reverse(), [...edges].reverse()), "root.py").candidates[0];
  assert.deepEqual(reversed, candidate);
});

test("three-file directed cycles are shown completely and unrelated cycles do not count", () => {
  const data = report([file("a.py"), file("b.py"), file("c.py"), file("entry.py")],
    [edge("a.py", "b.py"), edge("b.py", "c.py"), edge("c.py", "a.py"), edge("entry.py", "a.py")]);
  const candidate = repositoryProposals(data, "a.py").candidates[0];
  assert.deepEqual(candidate.before.nodes.map(item => item.id), ["a.py", "b.py", "c.py"]);
  assert.equal(candidate.before.edges.length, 3);
  assert.equal(candidate.after.edges.length, 2);
  assert.deepEqual(repositoryProposals(data, "entry.py").candidates, []);
  data.edges = [edge("a.py", "b.py"), edge("a.py", "c.py"), edge("b.py", "c.py")];
  assert.deepEqual(repositoryProposals(data, "a.py").candidates, []);
});

test("unknown endpoints, missing source evidence and self edges cannot create a proposed cycle", () => {
  const data = report([file("a.py")], [edge("a.py", "a.py"), edge("a.py", "missing.py"), edge("missing.py", "a.py")]);
  assert.deepEqual(repositoryProposals(data, "a.py").candidates, []);
  data.nodes.push(file("b.py"));
  data.edges = [edge("a.py", "b.py"), { source: "b.py", target: "a.py" }];
  assert.deepEqual(repositoryProposals(data, "a.py").candidates, []);
});

test("duplicate aliases are grouped as one pair while distinct source locations remain evidence", () => {
  const data = report([file("a.py"), file("b.py")],
    [edge("a.py", "b.py", 2), edge("a.py", "b.py", 2), edge("a.py", "b.py", 5), edge("b.py", "a.py", 7)]);
  const candidate = repositoryProposals(data, "a.py").candidates[0];
  assert.equal(candidate.before.edges.length, 2);
  assert.deepEqual(candidate.evidence.map(item => [item.path, item.line]), [["a.py", 2], ["b.py", 7], ["a.py", 5]]);
  assert.equal(candidate.omitted_evidence, 0);
});

test("long shortest cycles are explicitly omitted instead of being drawn as partial cycles", () => {
  const paths = Array.from({ length: 7 }, (_, index) => `module${index}.py`);
  const data = report(paths.map(path => file(path)), paths.map((path, index) => edge(path, paths[(index + 1) % paths.length])));
  const result = repositoryProposals(data, paths[0]);
  assert.deepEqual(result.candidates, []);
  assert.match(result.empty_reason, /파일 7개.*파일 6개 한도/);
  assert.match(result.limits.join("\n"), /일부 경로만 순환처럼 그리지/);
  data.nodes[0].declarations = [route(8), model(20)];
  const mixed = repositoryProposals(data, paths[0]);
  assert.deepEqual(mixed.candidates.map(item => item.id), ["separate-roles"]);
  assert.match(mixed.limits.join("\n"), /파일 7개/);
});

test("both supported rules can coexist without changing the observed report", () => {
  const data = report([file("a.py", [route(8), model(20)]), file("b.py")], [edge("a.py", "b.py"), edge("b.py", "a.py")]);
  const before = JSON.stringify(data);
  assert.deepEqual(repositoryProposals(data, "a.py").candidates.map(item => item.id), ["separate-roles", "break-cycle"]);
  assert.equal(JSON.stringify(data), before);
});

test("partial graph, declarations, source failure and unknown imports remain visible limits", () => {
  const data = report([file("a.py", [route(8), model(20)])]);
  Object.assign(data, { omitted_nodes: 4, omitted_edges: 9, omitted_unresolved: 3,
    unreadable_paths: ["bad.py"], warnings: ["unknown registration"], unresolved: [{ path: "a.py", line: 1 }] });
  data.nodes[0].omitted_declarations = 2;
  const limits = repositoryProposals(data, "a.py").limits.join("\n");
  for (const expected of [/파일 4개·관계 9개/, /직접 선언 2개/, /해석하지 못한 파일 1개/, /표시된 항목은 1건/, /전체 미확인 import 목록에서 3건/, /실제 실행 영향/]) assert.match(limits, expected);
});

test("text export includes hypothetical changes, scope and pinned real source evidence", () => {
  const data = report([file("main.py", [route(8), model(20)])]);
  const result = repositoryProposals(data, "main.py");
  const text = repositoryProposalText({ ...snapshot, warnings: ["raw source limit"] }, result, "separate-roles");
  assert.match(text, /미적용 가정/);
  assert.match(text, /Python 소스 루트: backend/);
  assert.match(text, /커밋: a{40}/);
  assert.match(text, /제안 구조 — 조건 충족 후의 가정/);
  assert.match(text, /추가 검토: 라우트 담당 역할 → 테이블 담당 역할/);
  assert.match(text, /https:\/\/github.com\/example\/demo\/blob\/a{40}\/main.py#L8/);
  assert.match(text, /https:\/\/github.com\/example\/demo\/blob\/a{40}\/main.py#L20/);
  assert.doesNotMatch(text, /blob\/[^\n]*proposal/);
  assert.match(text, /raw source limit/);
  assert.match(text, /범위: Python 원본 3개 중 구문 분석 1개/);
});

test("cycle export describes only the selected removal candidate and preserves omission count", () => {
  const data = report([file("a.py"), file("b.py")],
    [...Array.from({ length: 8 }, (_, index) => edge("a.py", "b.py", index + 1)), edge("b.py", "a.py", 3)]);
  const result = repositoryProposals(data, "a.py");
  assert.ok(result.candidates[0].evidence.some(item => item.path === "b.py" && item.line === 3));
  const text = repositoryProposalText(snapshot, result, "break-cycle");
  assert.match(text, /제거 검토: a.py → b.py/);
  assert.match(text, /근거 3곳은 목록 한도로 생략/);
  assert.match(text, /전체 순환이 해결.*뜻은 아닙니다/);
});

test("a six-file cycle retains evidence for every pair before remaining alias locations", () => {
  const paths = Array.from({ length: 6 }, (_, index) => `module${index}.py`);
  const edges = paths.map((path, index) => edge(path, paths[(index + 1) % paths.length], 3));
  edges.push(...Array.from({ length: 8 }, (_, index) => edge(paths[0], paths[1], index + 10)));
  const candidate = repositoryProposals(report(paths.map(path => file(path)), edges), paths[0]).candidates[0];
  assert.equal(candidate.before.nodes.length, 6);
  assert.equal(candidate.evidence.length, 6);
  assert.deepEqual(candidate.evidence.map(item => item.path), paths);
  assert.equal(candidate.omitted_evidence, 8);
});

test("export treats unusual source names as text and URL-encodes only real evidence paths", () => {
  const path = "app/a [draft]#?.py";
  const data = report([file(path, [route(8), { ...model(20), label: "Item\nnot a command" }])]);
  const result = repositoryProposals(data, path);
  const text = repositoryProposalText(snapshot, result, "separate-roles");
  assert.match(text, /선택 파일: app\/a \[draft\]#\?.py/);
  assert.match(text, /Item not a command/);
  assert.match(text, /\/app\/a%20%5Bdraft%5D%23%3F.py#L8/);
  assert.doesNotMatch(text, /\/blob\/[^\n]*proposal/);
});

test("unknown candidate IDs do not silently export a different candidate", () => {
  const result = repositoryProposals(report([file("main.py", [route(8), model(20)])]), "main.py");
  const text = repositoryProposalText(snapshot, result, "unknown");
  assert.match(text, /선택한 개선 후보를 찾을 수 없습니다/);
  assert.doesNotMatch(text, /후보: 라우트/);
});
