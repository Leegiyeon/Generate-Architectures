import test from "node:test";
import assert from "node:assert/strict";
import { reviewURL, reviewSettings } from "../app/pr_preview/review-link.js";

const site = "https://fastapi-pr-review-gyl.lgy.chatgpt.site/";
const pull = "https://github.com/fastapi-users/fastapi-users/pull/1258";
const hash = values => "#" + new URLSearchParams({ pr: pull, ...values }).toString();

test("a shared link restores the exact PR, perspective and repeated custom scope", () => {
  const options = {
    paths: ["backend/app", "src/한글 폴더/a+b.py"],
    models: ["src/orm.py:Account", "src/orm.py:Item"],
    responses: ["src/schema.py:AccountPublic"],
  };
  const url = new URL(reviewURL(site + "review?old=discard#results", pull + "/files?diff=split#L201", options, "db"));
  assert.equal(url.origin + url.pathname, site + "review");
  assert.equal(url.search, "");
  assert.deepEqual(reviewSettings(url.hash), { url: pull, focus: "db", options });
  assert.deepEqual(new URLSearchParams(url.hash.slice(1)).getAll("path"), options.paths);
});

test("defaults remain usable while ordinary anchors do not load review settings", () => {
  for (const value of ["", "#", "#results", "#focus=db"]) assert.equal(reviewSettings(value), null);
  assert.deepEqual(reviewSettings(new URL(reviewURL(site, pull)).hash), {
    url: pull, focus: "all", options: { paths: [], models: [], responses: [] },
  });
});

test("shared PR destinations reject other hosts, protocols and embedded credentials", () => {
  for (const invalid of [
    "https://example.com/a/b/pull/1", "http://github.com/a/b/pull/1",
    "javascript:alert(1)", "https://user:secret@github.com/a/b/pull/1",
  ]) {
    assert.throws(() => reviewURL(site, invalid));
    assert.throws(() => reviewSettings(hash({ pr: invalid })));
  }
});

test("ambiguous or unsupported settings are rejected rather than partially applied", () => {
  assert.throws(() => reviewURL(site, pull, {}, "invalid"));
  for (const invalid of [
    hash({ focus: "invalid" }), hash({ focus: "" }),
    hash({}) + "&pr=" + encodeURIComponent(pull),
    hash({ focus: "api" }) + "&focus=db", hash({ unexpected: "ignored" }),
  ]) assert.throws(() => reviewSettings(invalid));
});

test("scope entries preserve a 512 character boundary and reject control characters", () => {
  const valid = "x".repeat(512);
  assert.deepEqual(reviewSettings(new URL(reviewURL(site, pull, { paths: [valid] })).hash).options.paths, [valid]);
  for (const invalid of ["x".repeat(513), "backend\nother", "backend\rother", "backend\tother", "backend\0other", "backend\x7fother"]) {
    assert.throws(() => reviewURL(site, pull, { paths: [invalid] }));
    assert.throws(() => reviewSettings(hash({ path: invalid })));
  }
});

test("each repeated selector permits 30 entries and rejects a 31st without truncation", () => {
  for (const [option, key] of [["paths", "path"], ["models", "model"], ["responses", "response"]]) {
    const valid = Array.from({ length: 30 }, (_, index) => "src/m.py:Class" + index);
    const shared = new URL(reviewURL(site, pull, { [option]: valid }));
    assert.deepEqual(reviewSettings(shared.hash).options[option], valid);
    assert.throws(() => reviewURL(site, pull, { [option]: [...valid, "extra"] }));
    assert.throws(() => reviewSettings(shared.hash + "&" + key + "=extra"));
  }
});

test("an oversized complete link is rejected even when individual entries fit", () => {
  const options = { paths: Array(30).fill("x".repeat(500)) };
  assert.throws(() => reviewURL(site, pull, options));
  const parameters = new URLSearchParams({ pr: pull });
  for (const value of options.paths) parameters.append("path", value);
  assert.throws(() => reviewSettings("#" + parameters.toString()));
});
