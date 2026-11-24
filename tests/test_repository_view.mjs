import assert from "node:assert/strict";
import test from "node:test";
import { defaultRepositoryFile, repositoryFocus } from "../app/pr_preview/repository-view.js";

const file = path => ({ id: path, path });
test("file focus separates incoming and outgoing import evidence", () => {
  const report = { nodes: [file("a.py"), file("b.py"), file("c.py")], edges: [
    { source: "a.py", target: "b.py", evidence: { line: 1 } },
    { source: "c.py", target: "a.py", evidence: { line: 2 } },
    { source: "a.py", target: "b.py", evidence: { line: 3 } },
  ] };
  const outgoing = repositoryFocus(report, "a.py");
  assert.deepEqual(outgoing.neighbors.map(item => item.path), ["b.py"]);
  assert.equal(outgoing.edges.length, 2);
  const incoming = repositoryFocus(report, "a.py", "incoming");
  assert.deepEqual(incoming.neighbors.map(item => item.path), ["c.py"]);
  assert.equal(incoming.edges[0].evidence.line, 2);
});
test("diagram caps neighbors while preserving the full evidence list", () => {
  const paths = Array.from({ length: 15 }, (_, index) => `module${String(index).padStart(2, "0")}.py`);
  const report = { nodes: [file("entry.py"), ...paths.map(file)],
    edges: paths.map(path => ({ source: "entry.py", target: path })) };
  const focus = repositoryFocus(report, "entry.py");
  assert.equal(focus.neighbors.length, 12);
  assert.equal(focus.omitted_neighbors, 3);
  assert.equal(focus.edges.length, 15);
});
test("unknown file has no fabricated graph", () => {
  assert.deepEqual(repositoryFocus({ nodes: [], edges: [] }, "missing.py"),
    { selected: null, neighbors: [], edges: [], omitted_neighbors: 0 });
});
test("initial selection shows a route file or a known dependency instead of an empty initializer", () => {
  const empty = { ...file("__init__.py"), declarations: [] };
  const route = { ...file("routes.py"), declarations: [{ kind: "route" }] };
  assert.equal(defaultRepositoryFile({ nodes: [empty, route], edges: [] }), "routes.py");
  assert.equal(defaultRepositoryFile({ nodes: [empty, file("main.py")], edges: [{ source: "main.py", target: "__init__.py" }] }), "main.py");
  assert.equal(defaultRepositoryFile({ nodes: [], edges: [] }), undefined);
});
