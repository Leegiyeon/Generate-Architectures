import assert from "node:assert/strict";
import test from "node:test";

let moduleId = 0;
async function loader() {
  const url = new URL("../app/pr_preview/github.js", import.meta.url);
  url.searchParams.set("test", String(++moduleId));
  return import(url.href);
}

function publicPR(t, { beforeStatus = 200, changedHead = false,
    files = [{ filename: "app/new.py", previous_filename: "app/old.py", status: "renamed" }],
    totalFiles = files.length, source, onMetadata, onFiles } = {}) {
  const baseTip = "a".repeat(40), head = "b".repeat(40), mergeBase = "c".repeat(40);
  const endpoint = "https://api.github.com/repos/upstream/service/pulls/42";
  const beforeURL = `https://raw.githubusercontent.com/upstream/service/${mergeBase}/app/old.py`;
  const afterURL = `https://raw.githubusercontent.com/contributor/service/${head}/app/new.py`;
  const metadata = {
    title: "Rename account routes", changed_files: totalFiles,
    base: { sha: baseTip, repo: { full_name: "upstream/service", private: false } },
    head: { sha: head, repo: { full_name: "contributor/service", private: false } },
  };
  const requested = [];
  let metadataReads = 0;
  t.mock.method(globalThis, "fetch", async (url, options) => {
    requested.push(url);
    assert.equal(options.credentials, "omit");
    assert.equal(options.redirect, "error");
    if (url === endpoint) {
      metadataReads++;
      onMetadata?.(metadataReads);
      const current = structuredClone(metadata);
      if (changedHead && metadataReads > 1) current.head.sha = "d".repeat(40);
      return Response.json(current);
    }
    if (url === `https://api.github.com/repos/upstream/service/compare/${baseTip}...${head}?per_page=1`) {
      return Response.json({ merge_base_commit: { sha: mergeBase } });
    }
    if (url.startsWith(endpoint + "/files?per_page=100&page=")) {
      const page = Number(new URL(url).searchParams.get("page"));
      onFiles?.(page);
      return Response.json(files.slice((page - 1) * 100, page * 100));
    }
    if (url.startsWith("https://raw.githubusercontent.com/") && source) return source(url, options);
    if (url === beforeURL) return new Response("old_source = True\n", { status: beforeStatus });
    if (url === afterURL) return new Response("new_source = True\n");
    if (url.startsWith("https://raw.githubusercontent.com/")) return new Response("value = True\n");
    throw new Error("Unexpected request: " + url);
  });
  return { requested, beforeURL, afterURL, mergeBase, head };
}

test("canonicalizes HTTPS GitHub PR links and rejects other destinations", async () => {
  const { parsePullURL } = await loader();
  assert.deepEqual(parsePullURL(" https://github.com/upstream/service/pull/42/files?diff=split#L1 "), {
    repo: "upstream/service", number: "42", url: "https://github.com/upstream/service/pull/42",
  });
  for (const url of [
    "http://github.com/upstream/service/pull/42",
    "https://github.com.evil.example/upstream/service/pull/42",
    "https://github.com@evil.example/upstream/service/pull/42",
    "https://user:password@github.com/upstream/service/pull/42",
    "https://github.com:444/upstream/service/pull/42",
    "https://github.com/upstream/service/issues/42",
    "https://github.com/upstream/service/pull/0",
    "javascript:alert(1)",
  ]) assert.throws(() => parsePullURL(url), Error, url);
});

const pullURL = "https://github.com/upstream/service/pull/42";
const signal = () => new AbortController().signal;
const rawRequests = fixture => fixture.requested.filter(url => url.startsWith("https://raw.githubusercontent.com/"));
const modified = filename => ({ filename, status: "modified" });

test("path scope reserves the source limit for matching files beyond the first hundred", async t => {
  const fixture = publicPR(t, { files: [
    ...Array.from({ length: 100 }, (_, index) => modified(`docs/file${index}.py`)),
    modified("backend/target.py"),
  ] });
  const { loadPull } = await loader();
  const pull = await loadPull(pullURL, signal(), () => {}, ["backend"]);
  assert.equal(pull.files.length, 101);
  const target = pull.files.find(file => file.path === "backend/target.py");
  assert.equal(target.before, "value = True\n");
  assert.equal(target.after, "value = True\n");
  assert.deepEqual(target.warnings, []);
  assert.equal(rawRequests(fixture).length, 2);
  assert.ok(rawRequests(fixture).every(url => url.endsWith("/backend/target.py")));
});

test("path scope matches exact files and directory descendants without sibling prefixes", async t => {
  const fixture = publicPR(t, { files: ["app/routes.py", "app/nested/model.py", "application/outside.py", "other/one.py", "other/one.py.extra.py"].map(modified) });
  const { loadPull } = await loader();
  const pull = await loadPull(pullURL, signal(), () => {}, ["app///", "other/one.py"]);
  assert.deepEqual(pull.files.filter(file => file.after !== null).map(file => file.path), ["app/routes.py", "app/nested/model.py", "other/one.py"]);
  assert.equal(rawRequests(fixture).length, 6);
  assert.ok(pull.files.filter(file => file.after === null).every(file => !file.warnings.length));
});

test("cache separates source scopes and reuses reordered duplicate or trailing-slash scopes", async t => {
  const fixture = publicPR(t, { files: ["app/routes.py", "other/model.py", "third/module.py"].map(modified) });
  const { loadPull } = await loader();
  const app = await loadPull(pullURL, signal(), () => {}, ["app/"]);
  const reads = fixture.requested.length;
  assert.equal(await loadPull(pullURL + "/files", signal(), () => {}, ["app", "app///"]), app);
  assert.equal(fixture.requested.length, reads);
  const other = await loadPull(pullURL, signal(), () => {}, ["other"]);
  assert.equal(other.files.find(file => file.path === "other/model.py").after, "value = True\n");
  assert.equal(other.files.find(file => file.path === "app/routes.py").after, null);
  const combined = await loadPull(pullURL, signal(), () => {}, ["other", "app"]);
  const combinedReads = fixture.requested.length;
  assert.equal(await loadPull(pullURL, signal(), () => {}, ["app/", "other/", "app"]), combined);
  assert.equal(fixture.requested.length, combinedReads);
  const all = await loadPull(pullURL, signal(), () => {});
  assert.ok(all.files.every(file => file.before !== null && file.after !== null));
});

test("scoped renamed files match their current path while preserving old fork source paths", async t => {
  const fixture = publicPR(t, { files: [{ filename: "new/routes.py", previous_filename: "old/routes.py", status: "renamed" }] });
  const { loadPull } = await loader();
  const pull = await loadPull(pullURL, signal(), () => {}, ["new"]);
  assert.ok(pull.files[0].before !== null && pull.files[0].after !== null);
  assert.deepEqual(rawRequests(fixture), [
    `https://raw.githubusercontent.com/upstream/service/${fixture.mergeBase}/old/routes.py`,
    `https://raw.githubusercontent.com/contributor/service/${fixture.head}/new/routes.py`,
  ]);
  const reads = rawRequests(fixture).length;
  const old = await loadPull(pullURL, signal(), () => {}, ["old"]);
  assert.equal(old.files[0].before, null);
  assert.equal(rawRequests(fixture).length, reads);
});

test("scoped source collection retains both changed-list and matching Python file limits", async t => {
  const fixture = publicPR(t, { files: Array.from({ length: 301 }, (_, index) => modified(`app/file${index}.py`)) });
  const { loadPull } = await loader();
  const pull = await loadPull(pullURL, signal(), () => {}, ["app"]);
  assert.equal(pull.files.length, 300);
  assert.equal(pull.files.filter(file => file.after !== null).length, 100);
  assert.equal(rawRequests(fixture).length, 200);
  assert.match(pull.warnings.join(" "), /301.*300/);
  assert.ok(pull.files.slice(100).every(file => file.warnings.some(warning => warning.includes("100개"))));
  assert.ok(!fixture.requested.some(url => url.includes("page=4")));
});

test("empty path scopes retain Python filtering semantics and do not become an all-files request", async t => {
  const fixture = publicPR(t);
  const { loadPull } = await loader();
  const pull = await loadPull(pullURL, signal(), () => {}, ["///"]);
  assert.equal(pull.files[0].before, null);
  assert.equal(rawRequests(fixture).length, 0);
});

test("a pre-aborted request cannot access the network or return an existing cache entry", async t => {
  const fixture = publicPR(t);
  const { loadPull } = await loader();
  await assert.rejects(loadPull(pullURL, AbortSignal.abort(), () => {}), { name: "AbortError" });
  assert.equal(fixture.requested.length, 0);
  await loadPull(pullURL, signal(), () => {});
  const reads = fixture.requested.length;
  await assert.rejects(loadPull(pullURL, AbortSignal.abort(), () => {}), { name: "AbortError" });
  assert.equal(fixture.requested.length, reads);
});

test("abort after metadata or file-list resolution schedules no further requests", async t => {
  for (const stage of ["metadata", "files"]) {
    const controller = new AbortController();
    const fixture = publicPR(t, stage === "metadata" ? { onMetadata: () => controller.abort() } : { onFiles: () => controller.abort() });
    const { loadPull } = await loader();
    const messages = [];
    await assert.rejects(loadPull(pullURL, controller.signal, message => messages.push(message)), { name: "AbortError" });
    assert.equal(fixture.requested.length, stage === "metadata" ? 1 : 3);
    assert.equal(messages.length, 1);
    t.mock.restoreAll();
  }
});

test("abort during source collection emits no completion progress and can be retried", async t => {
  const controller = new AbortController();
  const fixture = publicPR(t, { source: () => { controller.abort(); return new Response("ignored = True\n"); } });
  const { loadPull } = await loader();
  const messages = [];
  await assert.rejects(loadPull(pullURL, controller.signal, message => messages.push(message)), { name: "AbortError" });
  assert.equal(rawRequests(fixture).length, 1);
  assert.equal(messages.length, 1);
  t.mock.restoreAll();
  const retryFixture = publicPR(t);
  const retry = await loadPull(pullURL, signal(), () => {});
  assert.equal(retry.files[0].before, "old_source = True\n");
  assert.equal(retryFixture.requested.length, 6);
});

test("abort at final PR verification cannot publish or cache a completed snapshot", async t => {
  const controller = new AbortController();
  publicPR(t, { onMetadata: reads => { if (reads === 2) controller.abort(); } });
  const { loadPull } = await loader();
  await assert.rejects(loadPull(pullURL, controller.signal, () => {}), { name: "AbortError" });
  t.mock.restoreAll();
  const fixture = publicPR(t);
  await loadPull(pullURL, signal(), () => {});
  assert.equal(fixture.requested.length, 6);
});

test("partial source failures do not cache an incomplete snapshot and retry can recover", async t => {
  publicPR(t, { beforeStatus: 404 });
  const { loadPull } = await loader();
  const partial = await loadPull(pullURL, signal(), () => {});
  assert.equal(partial.files[0].before, null);
  t.mock.restoreAll();
  const fixture = publicPR(t);
  const recovered = await loadPull(pullURL, signal(), () => {});
  assert.equal(recovered.files[0].before, "old_source = True\n");
  assert.deepEqual(recovered.files[0].warnings, []);
  assert.equal(fixture.requested.length, 6);
});

test("renamed fork files use the merge-base old path and pinned head new path", async t => {
  const fixture = publicPR(t);
  const { loadPull } = await loader();
  const pull = await loadPull("https://github.com/upstream/service/pull/42", new AbortController().signal, () => {});
  assert.equal(pull.base, fixture.mergeBase);
  assert.equal(pull.head, fixture.head);
  assert.equal(pull.files[0].before, "old_source = True\n");
  assert.equal(pull.files[0].after, "new_source = True\n");
  assert.deepEqual(pull.files[0].warnings, []);
  assert.ok(fixture.requested.includes(fixture.beforeURL));
  assert.ok(fixture.requested.includes(fixture.afterURL));
  assert.equal(fixture.requested.length, 6);
});

test("a failed source remains unknown with a warning instead of an empty deletion", async t => {
  publicPR(t, { beforeStatus: 404 });
  const { loadPull } = await loader();
  const pull = await loadPull("https://github.com/upstream/service/pull/42", new AbortController().signal, () => {});
  assert.equal(pull.files[0].before, null);
  assert.equal(pull.files[0].after, "new_source = True\n");
  assert.ok(pull.files[0].warnings.some(message => message.includes("이전") && message.includes("404")));
});

test("rejects a PR whose head changes during source collection", async t => {
  publicPR(t, { changedHead: true });
  const { loadPull } = await loader();
  await assert.rejects(
    loadPull("https://github.com/upstream/service/pull/42", new AbortController().signal, () => {}),
    /조회 중 PR 커밋이 바뀌었습니다/,
  );
});
