import test from "node:test";
import assert from "node:assert/strict";
import { feedbackURL } from "../app/pr_preview/feedback.js";

test("feedback opens a draft at the project's fixed issue destination", () => {
  const url = new URL(feedbackURL());
  assert.equal(url.origin + url.pathname, "https://github.com/Leegiyeon/Generate-Architectures/issues/new");
  assert.match(url.searchParams.get("body"), /공개 이슈로 등록/);
  assert.match(url.searchParams.get("body"), /다음 PR에서도/);
});

test("feedback preserves analyzed context including incomplete coverage", () => {
  const body = new URL(feedbackURL({url:"https://github.com/example/repo/pull/12",base:"a".repeat(40),head:"b".repeat(40)},
    {parsed_files:1,python_files:2}, {paths:["backend/app"],models:["app/models.py:User"]}, "db")).searchParams.get("body");
  assert.match(body, /PR: https:\/\/github.com\/example\/repo\/pull\/12/);
  assert.match(body, /관점: DB/);
  assert.match(body, /Python 비교: 1 \/ 2개/);
  assert.match(body, /경로: backend\/app/);
  assert.match(body, /DB 모델: app\/models.py:User/);
  assert.match(body, new RegExp("a".repeat(40) + " → " + "b".repeat(40)));
});

test("large custom scopes remain bounded and source bodies are excluded", () => {
  const url = new URL(feedbackURL({url:"https://github.com/example/repo/pull/12",files:[{after:"PRIVATE_SOURCE_BODY"}]},
    null,{paths:Array(100).fill("long-path".repeat(100))}));
  assert.ok(url.href.length < 5000);
  assert.match(url.searchParams.get("body"), /처음 5개만 포함/);
  assert.doesNotMatch(url.searchParams.get("body"), /PRIVATE_SOURCE_BODY|Python 비교/);
});
