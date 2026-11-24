import test from "node:test";
import assert from "node:assert/strict";
import { reviewURL, reviewSettings, repositoryURL, repositorySettings } from "../app/pr_preview/review-link.js";

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

const repository = "https://github.com/fastapi/sqlmodel";
const commit = "abcdef0123456789".repeat(2) + "abcdef01";
const repositoryHash = values => "#" + new URLSearchParams({ mode: "repository", repo: repository, commit, ...values }).toString();

test("repository links preserve a service subpath and the exact pinned selection", () => {
  const settings = { url: repository + ".git/?old=discard#readme", commit: " " + commit.toUpperCase() + " ",
    root: " src/한글 폴더/ ", file: "src/한글 폴더/a+b#c &d.py", direction: "incoming", purpose: "testing" };
  const shared = new URL(repositoryURL("https://leegiyeon.github.io/Generate-Architectures/?old=discard#results", settings));
  assert.equal(shared.origin + shared.pathname, "https://leegiyeon.github.io/Generate-Architectures/");
  assert.equal(shared.search, "");
  assert.deepEqual(repositorySettings(shared.hash), { ...settings, url: repository, commit,
    root: "src/한글 폴더" });
  assert.equal(new URLSearchParams(shared.hash.slice(1)).get("file"), settings.file);
});

test("minimal repository settings default their root and view without moving the commit", () => {
  const expected = { url: repository, commit, root: ".", file: "", direction: "outgoing", purpose: "onboarding" };
  assert.deepEqual(repositorySettings(repositoryHash({})), expected);
  assert.deepEqual(repositorySettings(new URL(repositoryURL(site, { url: repository, commit })).hash), expected);
  assert.equal(new URLSearchParams(new URL(repositoryURL(site, expected)).hash.slice(1)).has("file"), false);
  for (const value of ["", "#", "#results", "#repository-proposals", "#focus=db", hash({ focus: "db" })]) {
    assert.equal(repositorySettings(value), null);
  }
  assert.equal(reviewSettings(repositoryHash({})), null);
  assert.equal(reviewSettings(new URL(reviewURL(site, pull)).hash).url, pull);
});

test("repository links require a full immutable commit and repository mode", () => {
  for (const invalid of [undefined, "", "main", "heads/main", "a".repeat(39), "g".repeat(40), 123]) {
    assert.throws(() => repositoryURL(site, { url: repository, commit: invalid }));
    if (invalid !== undefined) assert.throws(() => repositorySettings(repositoryHash({ commit: String(invalid) })));
  }
  const missingCommit = new URLSearchParams({ mode: "repository", repo: repository });
  const missingMode = new URLSearchParams({ repo: repository, commit });
  assert.throws(() => repositorySettings("#" + missingCommit));
  assert.throws(() => repositorySettings("#" + missingMode));
  assert.throws(() => repositorySettings(repositoryHash({ mode: "unsupported" })));
  assert.throws(() => repositorySettings("#mode=repository"));
});

test("repository sharing rejects external destinations, credentials and unsafe service bases", () => {
  for (const invalid of ["https://example.com/a/b", "http://github.com/a/b", "javascript:alert(1)",
    "https://user:secret@github.com/a/b", "https://github.com/a/b/pull/1", "https://github.com:444/a/b"]) {
    assert.throws(() => repositoryURL(site, { url: invalid, commit }));
    assert.throws(() => repositorySettings(repositoryHash({ repo: invalid })));
  }
  for (const invalid of ["javascript:alert(1)", "file:///tmp/index.html", "https://user:secret@example.com/", "invalid"]) {
    assert.throws(() => repositoryURL(invalid, { url: repository, commit }));
  }
  assert.match(repositoryURL("http://127.0.0.1:8767/Generate-Architectures/", { url: repository, commit }), /^http:\/\/127\.0\.0\.1:8767\/Generate-Architectures\/#/);
});

test("repository settings reject mixed modes, unknown fields and every duplicate scalar", () => {
  for (const key of ["mode", "repo", "commit", "root", "file", "direction", "purpose"]) {
    const params = new URLSearchParams({ mode: "repository", repo: repository, commit, root: ".",
      file: "main.py", direction: "incoming", purpose: "change" });
    params.append(key, params.get(key));
    assert.throws(() => repositorySettings("#" + params), key);
  }
  for (const key of ["pr", "path", "focus", "unexpected"]) {
    assert.throws(() => repositorySettings(repositoryHash({ [key]: "unsupported" })), key);
  }
  assert.throws(() => reviewSettings(hash({ repo: repository, mode: "repository" })));
});

test("repository selections validate enums and literal paths within the source root", () => {
  for (const values of [{ direction: "" }, { direction: "both" }, { purpose: "" }, { purpose: "deployment" },
    { root: "../src" }, { root: "/src" }, { root: "C:/src" }, { root: "src//app" },
    { file: "../main.py" }, { file: "/main.py" }, { file: "src\\main.py" }, { file: "src//main.py" },
    { file: "main.js" }, { file: "src/./main.py" }, { file: "main.py\nother.py" },
    { root: "src", file: "srcish/main.py" }, { root: "src", file: "main.py" }]) {
    assert.throws(() => repositoryURL(site, { url: repository, commit, ...values }), JSON.stringify(values));
    assert.throws(() => repositorySettings(repositoryHash(values)), JSON.stringify(values));
  }
  assert.throws(() => repositoryURL(site, { url: repository, commit, root: 42 }));
  const selected = { url: repository, commit, root: "src/", file: "src/main.py", direction: "outgoing", purpose: "change" };
  assert.deepEqual(repositorySettings(new URL(repositoryURL(site, selected)).hash), { ...selected, root: "src" });
});

test("repository path limits reuse the reader boundary and never truncate long links", () => {
  const file = "x".repeat(997) + ".py";
  assert.equal(repositorySettings(new URL(repositoryURL(site, { url: repository, commit, file })).hash).file, file);
  assert.throws(() => repositoryURL(site, { url: repository, commit, file: "x" + file }));
  assert.throws(() => repositorySettings(repositoryHash({ file: "x" + file })));
  const encodedTooLong = "한".repeat(900) + ".py";
  assert.throws(() => repositoryURL(site, { url: repository, commit, file: encodedTooLong }), /너무 길어/);
  assert.throws(() => repositorySettings(repositoryHash({ file: encodedTooLong })), /너무 길어/);
});
