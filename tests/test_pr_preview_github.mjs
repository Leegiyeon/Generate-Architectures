import assert from "node:assert/strict";
import test from "node:test";

let moduleId = 0;
async function loader() {
  const url = new URL("../app/pr_preview/github.js", import.meta.url);
  url.searchParams.set("test", String(++moduleId));
  return import(url.href);
}

function publicPR(t, { beforeStatus = 200, changedHead = false } = {}) {
  const baseTip = "a".repeat(40), head = "b".repeat(40), mergeBase = "c".repeat(40);
  const endpoint = "https://api.github.com/repos/upstream/service/pulls/42";
  const beforeURL = `https://raw.githubusercontent.com/upstream/service/${mergeBase}/app/old.py`;
  const afterURL = `https://raw.githubusercontent.com/contributor/service/${head}/app/new.py`;
  const metadata = {
    title: "Rename account routes", changed_files: 1,
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
      const current = structuredClone(metadata);
      if (changedHead && metadataReads > 1) current.head.sha = "d".repeat(40);
      return Response.json(current);
    }
    if (url === `https://api.github.com/repos/upstream/service/compare/${baseTip}...${head}?per_page=1`) {
      return Response.json({ merge_base_commit: { sha: mergeBase } });
    }
    if (url === endpoint + "/files?per_page=100&page=1") {
      return Response.json([{ filename: "app/new.py", previous_filename: "app/old.py", status: "renamed" }]);
    }
    if (url === beforeURL) return new Response("old_source = True\n", { status: beforeStatus });
    if (url === afterURL) return new Response("new_source = True\n");
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
