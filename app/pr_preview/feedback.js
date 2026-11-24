const FEEDBACK_URL = "https://github.com/Leegiyeon/Generate-Architectures/issues/new";

export function feedbackURL(pull, report, options = {}, focus = "all") {
  const body = [
    "## 사용 경험", "- 역할과 확인하려던 내용: ", "- 도움이 된 내용 / 틀리거나 빠진 내용: ",
    "- 다음 PR에서도 다시 쓸지와 이유: ", "", "## 분석 상황",
    "- PR: " + (pull?.url || "직접 입력해 주세요."),
    "- 관점: " + ({ all: "전체", api: "API", db: "DB" }[focus] || "전체"),
  ];
  if (pull?.base && pull?.head) body.push("- 비교 커밋: " + pull.base + " → " + pull.head);
  if (report) body.push("- Python 비교: " + report.parsed_files + " / " + report.python_files + "개");
  for (const [key, label] of [["paths", "경로"], ["models", "DB 모델"], ["responses", "응답 모델"]]) {
    const values = options[key] || [];
    body.push("- " + label + ": " + (values.length ? values.slice(0, 5).map(value => value.replace(/[\r\n]/g, " ").slice(0, 120)).join(", ") : "기본값"));
    if (values.length > 5) body.push("  (처음 5개만 포함)");
  }
  body.push("", "공개 이슈로 등록됩니다. 제출 전에 내용을 확인하고 비밀값이나 개인정보를 제거해 주세요.");
  const url = new URL(FEEDBACK_URL);
  url.searchParams.set("title", "[FastAPI PR 리뷰] 사용 피드백");
  url.searchParams.set("body", body.join("\n"));
  return url.href;
}
