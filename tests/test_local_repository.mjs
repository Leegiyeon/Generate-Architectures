import assert from "node:assert/strict";
import test from "node:test";
import { loadLocalRepository } from "../app/pr_preview/local-repository.js";

function file(path, source = "value = 1\n", overrides = {}) {
  const bytes = typeof source === "string" ? new TextEncoder().encode(source) : source;
  const entry = { name: path.split("/").at(-1), webkitRelativePath: path, size: bytes.byteLength, reads: 0,
    async arrayBuffer() {
      entry.reads++;
      return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    }, ...overrides };
  return entry;
}
const signal = () => new AbortController().signal;

test("local snapshot reads selected UTF-8 sources without network, execution or a fabricated commit", async t => {
  const requests = [];
  t.mock.method(globalThis, "fetch", (...args) => { requests.push(args); throw new Error("No local analysis network"); });
  const source = 'from fastapi import FastAPI\napp = FastAPI()\nraise RuntimeError("must not execute")\n';
  const files = [file("Private Project/app/main.py", source), file("Private Project/app/__init__.py", "")];
  const progress = [];
  const snapshot = await loadLocalRepository(files, ".", signal(), message => progress.push(message));
  assert.deepEqual(requests, []);
  assert.equal(snapshot.source, "local");
  assert.equal(snapshot.kind, "repository");
  assert.equal(snapshot.repo, "Private Project");
  assert.equal(snapshot.head, "");
  assert.equal(snapshot.root, ".");
  assert.equal(snapshot.url, undefined);
  assert.equal(snapshot.resolvedFrom, undefined);
  assert.equal(snapshot.totalFiles, 2);
  assert.ok(Number.isFinite(Date.parse(snapshot.fetchedAt)));
  assert.deepEqual(snapshot.knownPaths, ["app/__init__.py", "app/main.py"]);
  assert.equal(snapshot.files[1].after, source);
  assert.equal(snapshot.files[0].after, "");
  assert.ok(snapshot.files.every(entry => Object.keys(entry).sort().join() === "after,path,warnings"));
  assert.match(snapshot.warnings.join(" "), /Git 커밋.*심볼릭 링크/);
  assert.match(progress.at(-1), /2 \/ 2/);
});

test("fresh selections never reuse earlier local file contents", async () => {
  const firstFile = file("private/app.py", "before = 1");
  const first = await loadLocalRepository([firstFile], ".", signal());
  const nextFile = file("private/app.py", "after = 2");
  const next = await loadLocalRepository([nextFile], ".", signal());
  const repeated = await loadLocalRepository([nextFile], ".", signal());
  assert.equal(first.files[0].after, "before = 1");
  assert.equal(next.files[0].after, "after = 2");
  assert.notEqual(repeated, next);
  assert.equal(firstFile.reads, 1);
  assert.equal(nextFile.reads, 2);
});

test("dependency folders, non-Python credentials and unsupported suffixes are never read", async () => {
  const excluded = [".git", ".venv", ".VENV", ".env", "venv", "env", "node_modules", "__pycache__",
    "site-packages", ".tox", ".nox", ".cache", ".mypy_cache", ".pytest_cache", ".ruff_cache", "__pypackages__"]
    .map(directory => file(`project/${directory}/nested/secret.py`));
  const nonPython = [".env", "id_rsa", "credentials.json", "secret.pem", "app/main.PY", "README.md"]
    .map(path => file("project/" + path));
  const kept = file("project/app/Main.py");
  const snapshot = await loadLocalRepository([...excluded, ...nonPython, kept], ".", signal());
  assert.deepEqual(snapshot.knownPaths, ["app/Main.py"]);
  assert.equal(snapshot.totalFiles, 1);
  assert.ok([...excluded, ...nonPython].every(entry => entry.reads === 0));
  assert.equal(kept.reads, 1);
  assert.match(snapshot.warnings.join(" "), /Python 파일 16개를 제외/);
  assert.match(snapshot.warnings.join(" "), /Python이 아닌 파일 6개/);
});

test("source root filters descendants before the read limit and preserves path case", async () => {
  const files = [file("project/backend/app/Main.py"), file("project/backend/app/main.py"),
    file("project/backend-other/main.py"), file("project/Backend/main.py"), file("project/outside.py")];
  const snapshot = await loadLocalRepository(files, " backend/ ", signal());
  assert.equal(snapshot.root, "backend");
  assert.deepEqual(snapshot.knownPaths, ["backend/app/Main.py", "backend/app/main.py"]);
  assert.deepEqual(files.map(entry => entry.reads), [1, 1, 0, 0, 0]);
  const empty = await loadLocalRepository(files, "missing", signal());
  assert.deepEqual(empty.files, []);
  assert.deepEqual(empty.knownPaths, []);
  assert.equal(empty.totalFiles, 0);
  assert.match(empty.warnings.join(" "), /소스 루트에서 분석 가능한 Python 파일을 찾지 못/);
});

test("invalid roots and a pre-aborted request cannot read or enumerate selected files", async () => {
  let enumerations = 0;
  const files = { *[Symbol.iterator]() { enumerations++; yield file("project/main.py"); } };
  for (const root of ["../app", "/app", "app//other", "app/../other", "app\\other", "C:/private", "app\0x", "app\u0085x", "app\u2028x"]) {
    await assert.rejects(loadLocalRepository(files, root, signal()), /상대 경로/);
  }
  const reason = new DOMException("already cancelled", "AbortError");
  await assert.rejects(loadLocalRepository(files, ".", AbortSignal.abort(reason)), error => error === reason);
  assert.equal(enumerations, 0);
});

test("empty selection and missing directory-relative paths have actionable errors", async () => {
  for (const files of [null, undefined, {}, 12]) {
    await assert.rejects(loadLocalRepository(files, ".", signal()), /프로젝트 폴더를 선택/);
  }
  await assert.rejects(loadLocalRepository([], ".", signal()), /폴더에 파일이 없습니다/);
  await assert.rejects(loadLocalRepository([file("main.py")], ".", signal()), /폴더 전체를 선택/);
  await assert.rejects(loadLocalRepository([file("")], ".", signal()), /상대 경로/);
  const snapshot = await loadLocalRepository([file("project/README.md")], ".", signal());
  assert.equal(snapshot.files.length, 0);
  assert.match(snapshot.warnings.join(" "), /Python 파일을 찾지 못/);
});

test("malformed, traversal, mixed-root and duplicate paths fail before reading content", async () => {
  for (const path of ["/project/main.py", "project/../outside.py", "project/./main.py", "project//main.py",
    "project\\main.py", "project/app\nname.py", "project/app\0name.py", "project/app\u0085name.py", "project/app\u2028name.py",
    "../app.py", "C:/project/main.py", "file:/private.py", "project/" + "a".repeat(1001) + ".py"]) {
    const entry = file(path);
    await assert.rejects(loadLocalRepository([entry], ".", signal()), Error, path);
    assert.equal(entry.reads, 0);
  }
  for (const paths of [["project/app.py", "other/app.py"], ["project/app.py", "Project/app.py"],
    ["project/app.py", "project/app.py"], ["project/README.md", "project/README.md"]]) {
    const entries = paths.map(path => file(path));
    await assert.rejects(loadLocalRepository(entries, ".", signal()), /여러 폴더|중복 경로/);
    assert.ok(entries.every(entry => entry.reads === 0));
  }
});

test("the selected source root reserves the 100-file budget and known paths retain omitted candidates", async () => {
  const outside = Array.from({ length: 110 }, (_, index) => file(`project/outside/f${index}.py`));
  const inside = Array.from({ length: 101 }, (_, index) => file(`project/src/f${String(index).padStart(3, "0")}.py`)).reverse();
  const snapshot = await loadLocalRepository([...outside, ...inside], "src", signal());
  assert.equal(snapshot.totalFiles, 101);
  assert.equal(snapshot.files.length, 100);
  assert.equal(snapshot.knownPaths.length, 101);
  assert.equal(snapshot.files[0].path, "src/f000.py");
  assert.equal(snapshot.files.at(-1).path, "src/f099.py");
  assert.equal(snapshot.knownPaths.at(-1), "src/f100.py");
  assert.ok(outside.every(entry => entry.reads === 0));
  assert.equal(inside[0].reads, 0);
  assert.match(snapshot.warnings.join(" "), /101개 중 100개.*나머지 1개/);
});

test("file-list iteration is bounded before any source read", async () => {
  let visited = 0;
  const entries = { *[Symbol.iterator]() {
    for (let index = 0; ; index++) { visited++; yield { webkitRelativePath: `project/f${index}.txt` }; }
  } };
  await assert.rejects(loadLocalRepository(entries, ".", signal()), /100,000개를 초과/);
  assert.equal(visited, 100001);
});

test("declared and actual bytes enforce the 64 KiB limit without truncating sources", async () => {
  const oversized = file("project/declared.py", "not read", { size: 65537 });
  const actualOversized = file("project/actual.py", "x".repeat(65537), { size: 1 });
  const boundary = file("project/boundary.py", "x".repeat(65536));
  const snapshot = await loadLocalRepository([oversized, actualOversized, boundary], ".", signal());
  assert.equal(oversized.reads, 0);
  assert.equal(actualOversized.reads, 1);
  assert.equal(boundary.reads, 1);
  assert.equal(snapshot.files.find(entry => entry.path === "boundary.py").after.length, 65536);
  for (const path of ["declared.py", "actual.py"]) {
    const entry = snapshot.files.find(entry => entry.path === path);
    assert.equal(entry.after, null);
    assert.match(entry.warnings.join(" "), /64 KiB/);
  }
  assert.match(snapshot.warnings.join(" "), /3개 중 2개의 소스를 읽지 못/);
});

test("read failures and invalid UTF-8 stay unknown without disclosing OS error paths", async () => {
  const entries = [file("project/good.py", "문자 = '정상'\n"),
    file("project/utf8.py", new Uint8Array([0xc3, 0x28])),
    file("project/denied.py", "", { arrayBuffer() { throw new Error("/Users/private/token=do-not-return"); } })];
  const snapshot = await loadLocalRepository(entries, ".", signal());
  assert.equal(snapshot.files.find(entry => entry.path === "good.py").after, "문자 = '정상'\n");
  assert.match(snapshot.files.find(entry => entry.path === "utf8.py").warnings.join(" "), /UTF-8/);
  assert.match(snapshot.files.find(entry => entry.path === "denied.py").warnings.join(" "), /접근 권한/);
  assert.equal(snapshot.files.filter(entry => entry.after === null).length, 2);
  assert.doesNotMatch(JSON.stringify(snapshot), /Users|do-not-return/);
  assert.deepEqual(snapshot.knownPaths, ["denied.py", "good.py", "utf8.py"]);
});

test("invalid selected file metadata stays unreadable instead of being accepted as empty source", async () => {
  const entries = [file("project/missing-size.py", "", { size: undefined }),
    file("project/negative-size.py", "", { size: -1 }),
    file("project/missing-reader.py", "", { arrayBuffer: undefined }),
    file("project/invalid-buffer.py", "", { async arrayBuffer() { return undefined; } })];
  const snapshot = await loadLocalRepository(entries, ".", signal());
  assert.ok(snapshot.files.every(entry => entry.after === null && entry.warnings.length));
  assert.ok(entries.every(entry => entry.reads === 0));
});

test("cancellation rejects pending reads immediately, caps concurrency and ignores late failures", async () => {
  const controller = new AbortController();
  const pending = [];
  const entries = Array.from({ length: 8 }, (_, index) => file(`project/f${index}.py`, "", {
    arrayBuffer() { return new Promise((resolve, reject) => pending.push({ resolve, reject })); },
  }));
  const progress = [];
  const loading = loadLocalRepository(entries, ".", controller.signal, message => progress.push(message));
  assert.equal(pending.length, 6);
  const reason = new DOMException("deadline exceeded", "TimeoutError");
  controller.abort(reason);
  await assert.rejects(loading, error => error === reason);
  for (const item of pending) item.reject(new Error("late read failure"));
  await Promise.resolve();
  assert.equal(pending.length, 6);
  assert.ok(progress.every(message => !/\d+ \/ \d+/.test(message)));
  const retry = await loadLocalRepository([file("project/fresh.py")], ".", signal());
  assert.equal(retry.files[0].after, "value = 1\n");
});

test("abort from progress cannot publish a completed snapshot or start queued reads", async () => {
  const controller = new AbortController();
  const entries = Array.from({ length: 8 }, (_, index) => file(`project/f${index}.py`));
  const loading = loadLocalRepository(entries, ".", controller.signal, message => {
    if (message.endsWith("1 / 8")) controller.abort();
  });
  await assert.rejects(loading, { name: "AbortError" });
  assert.equal(entries.reduce((total, entry) => total + entry.reads, 0), 6);
});
