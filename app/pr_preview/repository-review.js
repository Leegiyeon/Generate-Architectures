import { repositoryIdentityText, repositoryEvidenceText } from "./repository-source.js";

const PURPOSES = { onboarding: "온보딩", change: "변경 검토", testing: "테스트 계획" };
const MAX_EVIDENCE = 6;

function step(id, title, observation, action, check, locations) {
  const unique = [...new Map(locations.map(location => [
    JSON.stringify([location.path, location.line]), location,
  ])).values()];
  return { id, title, observation, action, check, evidence: unique.slice(0, MAX_EVIDENCE),
    omitted_evidence: Math.max(0, unique.length - MAX_EVIDENCE) };
}

export function repositoryReview(report, id, purpose = "onboarding") {
  if (!Object.hasOwn(PURPOSES, purpose)) purpose = "onboarding";
  const selected = report.nodes.find(item => item.id === id);
  const review = { purpose, title: PURPOSES[purpose], selected_path: selected?.path || null,
    summary: "선택한 파일을 찾을 수 없습니다. 표시된 파일에서 다시 선택하세요.", steps: [], limits: [],
    coverage: { displayed_files: report.nodes.length, displayed_edges: report.edges.length,
      parsed_files: report.parsed_files, incoming_files: 0, outgoing_files: 0, selected_unresolved: 0 } };
  if (!selected) return review;

  const incoming = report.edges.filter(edge => edge.target === id);
  const outgoing = report.edges.filter(edge => edge.source === id);
  const incomingFiles = new Set(incoming.map(edge => edge.source)).size;
  const outgoingFiles = new Set(outgoing.map(edge => edge.target)).size;
  const unresolved = (report.unresolved || []).filter(item => item.path === selected.path);
  const declarations = selected.declarations || [];
  const routes = declarations.filter(item => item.kind === "route");
  const models = declarations.filter(item => item.kind === "model");
  const fileEvidence = [{ path: selected.path, line: selected.line || 1, label: selected.path }];
  const declarationEvidence = items => items.map(item => ({ path: selected.path, line: item.line, label: item.label }));
  const edgeEvidence = edges => edges.map(edge => ({ ...edge.evidence, label: edge.label }));
  const displayed = `표시된 직접 선언: 라우트 ${routes.length}개·테이블 ${models.length}개`;
  review.summary = `${selected.path} · ${PURPOSES[purpose]}에 필요한 확인 순서입니다. 관찰한 코드와 제안한 행동을 함께 읽으세요.`;
  Object.assign(review.coverage, { incoming_files: incomingFiles, outgoing_files: outgoingFiles,
    selected_unresolved: unresolved.length });

  const declarationStep = step("declarations", declarations.length
    ? (purpose === "onboarding" ? "직접 선언부터 읽기" : "선언 계약 비교 준비")
    : (purpose === "onboarding" ? "원본에서 파일의 역할 확인" : "원본에서 사용 계약 확인"),
    displayed + ".",
    declarations.length
      ? (purpose === "onboarding"
        ? "라우트 핸들러·테이블의 직접 선언과 본문을 읽고 이 파일의 역할을 정리하세요. 최종 URL과 상속 필드는 원본에서 별도로 확인하세요."
        : "수정하려는 라우트의 입력·응답과 테이블 필드의 전후 차이를 PR 비교에서 확인하세요. 현재 스냅샷 하나만으로 변경 여부나 DB 호환성을 판단하지 마세요.")
      : (purpose === "onboarding"
        ? "원본의 함수·클래스와 사용 지점을 읽어 파일의 역할을 정리하세요. 선언 생략 안내가 있다면 함께 확인하세요. 지원하는 선언이 없다는 이유로 역할이 없다고 판단하지 마세요."
        : "원본의 함수·클래스와 실제 사용 지점을 확인한 뒤, 수정하려는 입력·반환값의 전후 차이를 PR 비교에서 확인하세요. 선언 생략 안내도 확인하세요."),
    purpose === "onboarding" ? "파일이 직접 맡는 역할과 아직 확인하지 못한 등록·상속 관계를 구분해 설명할 수 있는지 확인하세요."
      : (declarations.length ? "의도한 계약 변경과 이를 사용하는 코드·기존 데이터의 확인 항목을 적었는지 확인하세요."
        : "바꾸려는 동작과 실제로 사용하는 코드, 아직 확인하지 못한 부분을 구분했는지 확인하세요."),
    declarations.length ? declarationEvidence(declarations) : fileEvidence);

  const importsStep = step("imports", purpose === "testing" ? "테스트 준비의 참조 경계 확인" : "직접 참조를 따라 읽기",
    `표시된 그래프에서 이 파일의 직접 import 관계 ${outgoing.length}개가 파일 ${outgoingFiles}개를 가리킵니다.`,
    outgoing.length
      ? (purpose === "testing" ? "각 import의 실제 사용 지점을 읽고 테스트에 필요한 설정·데이터·대체 대상을 정하세요. import만으로 외부 호출이나 DB 접근을 가정하지 마세요."
        : "import문에서 사용하는 이름과 대상 파일의 직접 선언을 함께 읽어 어떤 역할을 가져오는지 확인하세요.")
      : "원본의 import와 아래 미확인 범위를 확인하세요. 표시된 연결이 없다는 이유로 독립적인 파일이라고 판단하지 마세요.",
    purpose === "testing" ? "실제로 사용한 의존성과 테스트 준비 조건을 코드 근거에 연결했는지 확인하세요. 테스트 실행 여부는 별도로 기록하세요."
      : "참조한 이름의 역할과 재수출·동적 로딩 등 미확인 부분을 구분했는지 확인하세요.",
    outgoing.length ? edgeEvidence(outgoing) : fileEvidence);

  if (purpose === "onboarding") review.steps.push(declarationStep, importsStep);
  else if (purpose === "change") {
    review.steps.push(step("consumers", "직접 참조하는 사용 지점 검토",
      `표시된 그래프에서 파일 ${incomingFiles}개가 직접 import 관계 ${incoming.length}개로 선택 파일을 참조합니다.`,
      incoming.length ? "이 import문의 실제 사용 지점을 먼저 읽고 변경하려는 이름·입력·반환값을 사용하는지 확인하세요. 사용이 확인된 곳의 관련 회귀 검사를 정하세요."
        : "원본 검색과 미확인 import를 함께 확인하세요. 표시된 참조가 없다는 이유로 변경 영향이 없다고 판단하지 마세요.",
      "각 검토 대상이 변경한 계약을 실제로 사용하는지 확인하고, 그래프에 없는 간접 사용은 별도로 조사했는지 확인하세요.",
      incoming.length ? edgeEvidence(incoming) : fileEvidence), declarationStep);
  } else {
    if (routes.length) review.steps.push(step("route-tests", "라우트 계약의 테스트 후보 정리",
      `선택 파일에 표시된 라우트 직접 선언 ${routes.length}개가 있습니다.`,
      "핸들러의 입력·검증·응답과 필요한 권한 조건을 원본에서 확인해 정상·실패 사례를 정하세요. 실제 등록 경로는 별도로 확인하세요.",
      "각 후보에 기대 결과와 근거가 있는지 확인한 뒤 실제 테스트를 실행하고 결과를 별도로 기록하세요.", declarationEvidence(routes)));
    if (models.length) review.steps.push(step("model-tests", "테이블 선언의 테스트 후보 정리",
      `선택 파일에 표시된 테이블 직접 선언 ${models.length}개가 있습니다.`,
      "직접 필드의 타입·기본값·제약을 읽고 검증할 입력과 저장·조회 사례를 정하세요. 상속 필드·실제 DB 제약·마이그레이션은 별도로 확인하세요.",
      "선언 검증과 실제 DB 동작을 구분하고, 적용한 DB·데이터 조건과 테스트 결과를 별도로 기록하세요.", declarationEvidence(models)));
    if (!routes.length && !models.length) review.steps.push(step("test-scope", "원본에서 검증할 동작 정하기",
      "표시된 목록에 지원하는 라우트·테이블 직접 선언이 없습니다.",
      "원본의 함수·클래스와 실제 사용 지점을 읽고 검증할 동작을 정하세요. 이 목록은 기존 테스트의 유무나 파일의 역할을 판정하지 않습니다.",
      "검증할 동작마다 입력·기대 결과와 기존 테스트의 위치를 직접 확인했는지 점검하세요.", fileEvidence));
    review.steps.push(importsStep);
  }

  review.limits.push("표시된 직접 import·선언에 따른 검토 제안입니다. 실제 실행 영향·최종 라우터 등록·기존 테스트의 존재·성공 여부는 확인하지 않았습니다.");
  if (report.omitted_nodes || report.omitted_edges) review.limits.push(`그래프 표시 범위에서 파일 ${report.omitted_nodes || 0}개·관계 ${report.omitted_edges || 0}개가 생략되어 참조 수는 전체가 아닐 수 있습니다.`);
  if (selected.omitted_declarations) review.limits.push(`선택 파일의 직접 선언 ${selected.omitted_declarations}개가 생략되어 선언 수와 테스트 후보는 표시된 목록 기준입니다.`);
  if (report.unreadable_paths?.length) review.limits.push(`소스를 읽거나 해석하지 못한 파일 ${report.unreadable_paths.length}개가 있습니다. 해당 파일의 선언·참조는 확인하지 못했습니다.`);
  if (unresolved.length) review.limits.push(`선택 파일의 미확인 import 중 목록에 표시된 항목은 ${unresolved.length}건입니다. 외부 패키지·조건부·동적 import 등이 포함되며 실제 오류 수를 뜻하지 않습니다.`);
  if (report.omitted_unresolved) review.limits.push(`전체 미확인 import 목록에서 ${report.omitted_unresolved}건을 생략했으므로 선택 파일의 미확인 수 역시 완전하지 않을 수 있습니다.`);
  if (report.warnings?.length) review.limits.push(`해석 한도와 추가 확인 안내 ${report.warnings.length}건도 함께 확인하세요.`);
  return review;
}

function oneLine(value) { return String(value).replace(/[\r\n]+/g, " "); }

export function repositoryReviewText(snapshot, review) {
  const lines = ["저장소 구조 검토 계획", ...repositoryIdentityText(snapshot),
    `Python 소스 루트: ${oneLine(snapshot.root)}`, `선택 파일: ${oneLine(review.selected_path || "미선택")}`,
    `목적: ${review.title}`, oneLine(review.summary)];
  if (review.coverage) lines.push(`범위: Python 원본 ${snapshot.totalFiles}개 중 구문 분석 ${review.coverage.parsed_files}개, 그래프 파일 ${review.coverage.displayed_files}개·관계 ${review.coverage.displayed_edges}개 표시`);
  for (const [index, item] of review.steps.entries()) {
    lines.push("", `${index + 1}. ${item.title}`, `관찰: ${oneLine(item.observation)}`,
      `할 일: ${oneLine(item.action)}`, `확인 기준: ${oneLine(item.check)}`);
    for (const evidence of item.evidence) lines.push(`근거: ${oneLine(evidence.label)} (${oneLine(evidence.path)}:${evidence.line})`,
      repositoryEvidenceText(snapshot, evidence.path, evidence.line));
    if (item.omitted_evidence) lines.push(`이 항목의 근거 ${item.omitted_evidence}개는 목록 한도로 생략했습니다.`);
  }
  lines.push("", "한도와 미확인 범위", ...review.limits.map(oneLine), ...(snapshot.warnings || []).map(oneLine));
  return lines.join("\n");
}
