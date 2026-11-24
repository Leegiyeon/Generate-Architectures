import assert from "node:assert/strict";
import test from "node:test";

let moduleId = 0;
const head = "a".repeat(40), treeSHA = "b".repeat(40);
const repository = "example/service";
const api = "https://api.github.com/repos/" + repository;
const raw = "https://raw.githubusercontent.com/" + repository + "/" + head + "/";
const entry = (path, extra = {}) => ({ path, mode: "100644", type: "blob", size: 20, ...extra });

async function loader() {
  const url = new URL("../app/pr_preview/repository.js", import.meta.url);
  url.searchParams.set("test", String(++moduleId));
  return import(url.href);
}

function fixture(t, { entries = [entry("app/main.py")], truncated = false, privateRepo = false, source, onTree,
  defaultBranch = "main", resolvedCommit = { sha: head, commit: { tree: { sha: treeSHA } } }, resolveStatus = 200, onResolve } = {}) {
  const requests = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    requests.push(url);
    assert.equal(options.credentials, "omit");
    assert.equal(options.redirect, "error");
    options.signal.throwIfAborted();
    if (url === api) return Response.json({ full_name: repository, private: privateRepo, default_branch: defaultBranch });
    if (url === api + "/commits/" + encodeURIComponent("heads/" + defaultBranch) + "?per_page=1") {
      onResolve?.();
      return Response.json(resolvedCommit, { status: resolveStatus });
    }
    if (url === api + "/git/commits/" + head) return Response.json({ sha: head, tree: { sha: treeSHA } });
    if (url === api + "/git/trees/" + treeSHA + "?recursive=1") {
      onTree?.();
      return Response.json({ sha: treeSHA, tree: entries, truncated });
    }
    if (url.startsWith(raw)) return source ? source(decodeURIComponent(url.slice(raw.length)), options) : new Response("from fastapi import FastAPI\n");
    throw new Error("Unexpected request: " + url);
  });
  return requests;
}

test("repository links canonicalize root URLs and reject other destinations", async () => {
  const { parseRepositoryURL } = await loader();
  assert.deepEqual(parseRepositoryURL(" https://github.com/example/service.git/?x=1#readme "), {
    repo: repository, url: "https://github.com/" + repository,
  });
  for (const input of [
    "http://github.com/example/service", "https://github.com.evil.example/example/service",
    "https://github.com@evil.example/example/service", "https://user:pass@github.com/example/service",
    "https://github.com:444/example/service", "https://github.com/example/service/tree/main",
    "https://github.com/example/service/pull/42", "https://github.com/example/.git", "javascript:alert(1)",
  ]) assert.throws(() => parseRepositoryURL(input), Error, input);
});

test("invalid commit/root and pre-aborted requests fail before network access", async t => {
  const { loadRepository } = await loader();
  const requests = fixture(t);
  for (const commit of ["main", "abc123", "z".repeat(40), null, false, 42]) {
    await assert.rejects(loadRepository("https://github.com/" + repository, commit, ".", new AbortController().signal), /SHA/);
  }
  for (const root of ["/app", "../app", "app/..", "app//other", "app\\other", "app/./other", "app\0other", "C:/work", "C:work"]) {
    await assert.rejects(loadRepository("https://github.com/" + repository, head, root, new AbortController().signal), /상대 경로/);
  }
  const aborted = AbortSignal.abort();
  await assert.rejects(loadRepository("https://github.com/" + repository, head, ".", aborted), { name: "AbortError" });
  await assert.rejects(loadRepository("https://github.com/" + repository, "", ".", aborted), { name: "AbortError" });
  assert.deepEqual(requests, []);
});

test("blank commit resolves the explicit default-branch ref and pins every source read", async t => {
  const { loadRepository } = await loader();
  const branch = "release/latest";
  const requests = fixture(t, { defaultBranch: branch });
  const snapshot = await loadRepository("https://github.com/" + repository, "  ", ".", new AbortController().signal);
  assert.equal(snapshot.head, head);
  assert.deepEqual(snapshot.resolvedFrom, { branch });
  assert.equal(snapshot.files[0].after, "from fastapi import FastAPI\n");
  assert.deepEqual(requests, [api, api + "/commits/heads%2Frelease%2Flatest?per_page=1",
    api + "/git/trees/" + treeSHA + "?recursive=1", raw + "app/main.py"]);
  assert.ok(!requests.some(url => url.includes("/tags/") || url.includes("/git/commits/")));
  const explicit = await loadRepository("https://github.com/" + repository, head, ".", new AbortController().signal);
  assert.equal(explicit.resolvedFrom, undefined);
  assert.equal(explicit.files, snapshot.files);
  assert.equal(requests.length, 4);
});

test("every blank or omitted commit resolves latest before reusing immutable source cache", async t => {
  const { loadRepository } = await loader();
  const requests = fixture(t);
  const first = await loadRepository("https://github.com/" + repository, undefined, ".", new AbortController().signal);
  const second = await loadRepository("https://github.com/" + repository, "", ".", new AbortController().signal);
  assert.equal(second.head, head);
  assert.deepEqual(second.resolvedFrom, { branch: "main" });
  assert.equal(second.files, first.files);
  assert.equal(requests.filter(url => url === api).length, 2);
  assert.equal(requests.filter(url => url.includes("/commits/heads%2Fmain")).length, 2);
  assert.equal(requests.filter(url => url.includes("/git/trees/")).length, 1);
  assert.equal(requests.filter(url => url.startsWith(raw)).length, 1);
});

test("latest follows a moved default-branch tip and never uses branch raw URLs", async t => {
  const { loadRepository } = await loader();
  const nextHead = "c".repeat(40), nextTree = "d".repeat(40);
  const requests = [];
  let currentHead = head, currentTree = treeSHA;
  t.mock.method(globalThis, "fetch", async (url, options) => {
    requests.push(url);
    options.signal.throwIfAborted();
    if (url === api) return Response.json({ full_name: repository, private: false, default_branch: "main" });
    if (url === api + "/commits/heads%2Fmain?per_page=1") {
      return Response.json({ sha: currentHead, commit: { tree: { sha: currentTree } } });
    }
    if (url === api + "/git/trees/" + currentTree + "?recursive=1") {
      return Response.json({ sha: currentTree, tree: [entry("app/main.py")], truncated: false });
    }
    if (url === "https://raw.githubusercontent.com/" + repository + "/" + currentHead + "/app/main.py") {
      return new Response(currentHead === head ? "before = 1" : "after = 2");
    }
    throw new Error("Unexpected request: " + url);
  });
  const read = () => loadRepository("https://github.com/" + repository, "", ".", new AbortController().signal);
  const before = await read();
  currentHead = nextHead; currentTree = nextTree;
  const after = await read();
  assert.equal(before.head, head);
  assert.equal(after.head, nextHead);
  assert.equal(after.files[0].after, "after = 2");
  currentHead = head; currentTree = treeSHA;
  const restored = await read();
  assert.equal(restored.files, before.files);
  assert.equal(requests.filter(url => url.includes("/commits/heads%2Fmain")).length, 3);
  assert.equal(requests.filter(url => url.startsWith("https://raw.githubusercontent.com/")).length, 2);
});

test("latest rejects private/missing branches and malformed commits before source reads", async t => {
  const cases = [
    { options: { privateRepo: true }, message: /공개 저장소만/, count: 1 },
    ...[null, "", "bad branch", "bad\nbranch"].map(defaultBranch => ({ options: { defaultBranch }, message: /기본 브랜치/, count: 1 })),
    ...[null, {}, { sha: "main", commit: { tree: { sha: treeSHA } } },
      { sha: head, tree: { sha: treeSHA } }, { sha: head, commit: { tree: { sha: "invalid" } } },
      { sha: [head], commit: { tree: { sha: treeSHA } } },
      { sha: head, commit: { tree: { sha: [treeSHA] } } }].map(resolvedCommit => ({ options: { resolvedCommit }, message: /커밋과 파일 목록/, count: 2 })),
    { options: { resolveStatus: 404 }, message: /찾을 수 없습니다/, count: 2 },
    { options: { truncated: true }, message: /목록이 잘렸/, count: 3 },
  ];
  for (const { options, message, count } of cases) {
    t.mock.restoreAll();
    const { loadRepository } = await loader();
    const requests = fixture(t, options);
    await assert.rejects(loadRepository("https://github.com/" + repository, "", ".", new AbortController().signal), message);
    assert.equal(requests.length, count);
    assert.ok(requests.every(url => !url.startsWith("https://raw.githubusercontent.com/")));
  }
});

test("latest resolution failure and abort do not create a reusable snapshot", async t => {
  const { loadRepository } = await loader();
  let requests = fixture(t, { resolveStatus: 404 });
  await assert.rejects(loadRepository("https://github.com/" + repository, "", ".", new AbortController().signal), /찾을 수 없습니다/);
  assert.equal(requests.length, 2);
  t.mock.restoreAll();
  const controller = new AbortController();
  requests = fixture(t, { onTree: () => controller.abort() });
  await assert.rejects(loadRepository("https://github.com/" + repository, "", ".", controller.signal), { name: "AbortError" });
  assert.ok(!requests.some(url => url.startsWith(raw)));
  t.mock.restoreAll();
  requests = fixture(t);
  const retry = await loadRepository("https://github.com/" + repository, "", ".", new AbortController().signal);
  assert.equal(retry.files.length, 1);
  assert.ok(requests.includes(raw + "app/main.py"));
});

test("aborted latest resolution cannot return a previously cached snapshot", async t => {
  const { loadRepository } = await loader();
  fixture(t);
  const first = await loadRepository("https://github.com/" + repository, "", ".", new AbortController().signal);
  t.mock.restoreAll();
  const controller = new AbortController();
  const requests = fixture(t, { onResolve: () => controller.abort() });
  await assert.rejects(loadRepository("https://github.com/" + repository, "", ".", controller.signal), { name: "AbortError" });
  assert.equal(requests.length, 2);
  t.mock.restoreAll();
  fixture(t);
  const retry = await loadRepository("https://github.com/" + repository, "", ".", new AbortController().signal);
  assert.equal(retry.files, first.files);
});

test("fixed commit raw URLs obey root, file kind and declared size limits", async t => {
  const entries = [
    entry("backend/app/main.py"), entry("backend/app/empty.py"), entry("backend/app/large.py", { size: 65537 }),
    entry("backend/app/link.py", { mode: "120000" }), entry("backend/submodule.py", { type: "commit", mode: "160000" }),
    entry("backend-other/outside.py"), entry("tests/outside.py"), entry("backend/README.md"),
  ];
  const requested = fixture(t, { entries, source: path => new Response(path.endsWith("empty.py") ? "" : "x = 1\n") });
  const { loadRepository } = await loader();
  const snapshot = await loadRepository("https://github.com/" + repository, head.toUpperCase(), "backend/", new AbortController().signal);
  assert.equal(snapshot.kind, "repository");
  assert.equal(snapshot.head, head);
  assert.equal(snapshot.headRepo, repository);
  assert.equal(snapshot.root, "backend");
  assert.equal(snapshot.totalFiles, 3);
  assert.deepEqual(snapshot.knownPaths, ["backend/app/empty.py", "backend/app/large.py", "backend/app/link.py", "backend/app/main.py"]);
  assert.deepEqual(snapshot.files.map(file => file.path), ["backend/app/empty.py", "backend/app/large.py", "backend/app/main.py"]);
  assert.equal(snapshot.files[0].after, "");
  assert.equal(snapshot.files[1].after, null);
  assert.match(snapshot.files[1].warnings[0], /64 KiB/);
  assert.equal(requested.filter(url => url.startsWith(raw)).length, 2);
  assert.ok(requested.includes(raw + "backend/app/main.py"));
  assert.ok(snapshot.warnings.some(message => message.includes("2개를 제외")));
  assert.ok(snapshot.warnings.some(message => message.includes("1개의 소스")));
});

test("truncated trees and private metadata are rejected without reading source", async t => {
  const { loadRepository } = await loader();
  const requests = fixture(t, { truncated: true });
  await assert.rejects(loadRepository("https://github.com/" + repository, head, ".", new AbortController().signal), /목록이 잘렸/);
  assert.equal(requests.filter(url => url.startsWith(raw)).length, 0);
  t.mock.restoreAll();
  const privateRequests = fixture(t, { privateRepo: true });
  await assert.rejects(loadRepository("https://github.com/" + repository, head, ".", new AbortController().signal), /공개 저장소만/);
  assert.deepEqual(privateRequests, [api]);
});

test("source read failures remain unknown and partial snapshots are not cached", async t => {
  const { loadRepository } = await loader();
  const requests = fixture(t, { source: () => new Response("missing", { status: 404 }) });
  const first = await loadRepository("https://github.com/" + repository, head, ".", new AbortController().signal);
  assert.equal(first.files[0].after, null);
  assert.match(first.files[0].warnings[0], /HTTP 404/);
  await loadRepository("https://github.com/" + repository, head, ".", new AbortController().signal);
  assert.equal(requests.filter(url => url === api).length, 2);
});

test("streamed source size and UTF-8 errors are bounded and unknown", async t => {
  const { loadRepository } = await loader();
  fixture(t, { entries: [entry("oversized.py"), entry("invalid.py")], source: path => new Response(
    path === "oversized.py" ? "x".repeat(65537) : new Uint8Array([0xff, 0xff]),
  ) });
  const value = await loadRepository("https://github.com/" + repository, head, ".", new AbortController().signal);
  assert.ok(value.files.every(file => file.after === null));
  assert.ok(value.files.some(file => file.warnings.some(message => message.includes("64 KiB"))));
  assert.ok(value.files.some(file => file.warnings.some(message => message.includes("UTF-8"))));
});

test("tree path traversal is rejected before raw source requests", async t => {
  const { loadRepository } = await loader();
  const requests = fixture(t, { entries: [entry("app/../outside.py")] });
  await assert.rejects(loadRepository("https://github.com/" + repository, head, ".", new AbortController().signal), /올바르지 않은 경로/);
  assert.equal(requests.filter(url => url.startsWith(raw)).length, 0);
});

test("100-file limit and six parallel source requests are enforced", async t => {
  const { loadRepository } = await loader();
  let active = 0, maximum = 0;
  const entries = Array.from({ length: 102 }, (_, index) => entry(`app/file${String(index).padStart(3, "0")}.py`));
  const requests = fixture(t, { entries, source: async () => {
    active++;
    maximum = Math.max(maximum, active);
    await new Promise(resolve => setTimeout(resolve, 1));
    active--;
    return new Response("x = 1");
  } });
  const snapshot = await loadRepository("https://github.com/" + repository, head, ".", new AbortController().signal);
  assert.equal(snapshot.totalFiles, 102);
  assert.equal(snapshot.files.length, 100);
  assert.equal(requests.filter(url => url.startsWith(raw)).length, 100);
  assert.equal(maximum, 6);
  assert.ok(snapshot.warnings.some(message => message.includes("나머지 2개")));
});

test("known paths retain an unselected package initializer at the 100-file boundary", async t => {
  const { loadRepository } = await loader();
  const entries = [entry("main.py"), entry("target.py"),
    ...Array.from({ length: 98 }, (_, index) => entry(`target/A${String(index).padStart(2, "0")}.py`)),
    entry("target/__init__.py")];
  const requests = fixture(t, { entries });
  const snapshot = await loadRepository("https://github.com/" + repository, head, ".", new AbortController().signal);
  assert.equal(snapshot.totalFiles, 101);
  assert.equal(snapshot.knownPaths.length, 101);
  assert.ok(snapshot.knownPaths.includes("target.py"));
  assert.ok(snapshot.knownPaths.includes("target/__init__.py"));
  assert.equal(snapshot.files.length, 100);
  assert.ok(snapshot.files.some(file => file.path === "target.py"));
  assert.ok(!snapshot.files.some(file => file.path === "target/__init__.py"));
  assert.equal(requests.filter(url => url.startsWith(raw)).length, 100);
  const cached = await loadRepository("https://github.com/" + repository, head, ".", new AbortController().signal);
  assert.equal(cached, snapshot);
  assert.deepEqual(cached.knownPaths, snapshot.knownPaths);
});

test("duplicate paths including skipped symlink blobs are rejected", async t => {
  const { loadRepository } = await loader();
  const requests = fixture(t, { entries: [entry("target.py", { mode: "120000" }), entry("target.py")] });
  await assert.rejects(loadRepository("https://github.com/" + repository, head, ".", new AbortController().signal), /중복 경로/);
  assert.equal(requests.filter(url => url.startsWith(raw)).length, 0);
});

test("abort during a source read propagates and is not cached", async t => {
  const { loadRepository } = await loader();
  const controller = new AbortController();
  const requests = fixture(t, { source: () => { controller.abort(); throw controller.signal.reason; } });
  await assert.rejects(loadRepository("https://github.com/" + repository, head, ".", controller.signal), { name: "AbortError" });
  t.mock.restoreAll();
  const retryRequests = fixture(t);
  const retry = await loadRepository("https://github.com/" + repository, head, ".", new AbortController().signal);
  assert.equal(retry.files.length, 1);
  assert.ok(requests.length >= 4);
  assert.ok(retryRequests.includes(api));
});

test("a late completed source after cancellation cannot publish progress or cache", async t => {
  const { loadRepository } = await loader();
  const controller = new AbortController();
  fixture(t, { source: () => { controller.abort(); return new Response("value = 1\n"); } });
  const messages = [];
  await assert.rejects(loadRepository("https://github.com/" + repository, head, ".", controller.signal,
    message => messages.push(message)), { name: "AbortError" });
  assert.equal(messages.some(message => message.startsWith("고정 커밋의 Python 소스")), false);
  t.mock.restoreAll();
  const retryRequests = fixture(t);
  await loadRepository("https://github.com/" + repository, head, ".", new AbortController().signal);
  assert.ok(retryRequests.includes(api));
});

test("successful cache is keyed by commit/root, capped at two and expires after three minutes", async t => {
  const { loadRepository } = await loader();
  const requests = fixture(t);
  let now = 10000;
  t.mock.method(Date, "now", () => now);
  const read = root => loadRepository("https://github.com/" + repository, head, root, new AbortController().signal);
  const first = await read(".");
  assert.equal(await read("."), first);
  assert.equal(requests.filter(url => url === api).length, 1);
  await read("app");
  await read("other");
  assert.notEqual(await read("."), first);
  assert.equal(requests.filter(url => url === api).length, 4);
  now += 180001;
  await read(".");
  assert.equal(requests.filter(url => url === api).length, 5);
});
