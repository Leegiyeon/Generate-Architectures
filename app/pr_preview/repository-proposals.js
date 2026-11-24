import { sourceURL } from "./github.js";
import { repositoryReview } from "./repository-review.js";

const MAX_EVIDENCE = 6;
const MAX_CYCLE_NODES = 6;
const ROUTE_ROLE = "proposal:route-role";
const TABLE_ROLE = "proposal:table-role";
const compare = (left, right) => left < right ? -1 : left > right ? 1 : 0;
const pairKey = (source, target) => JSON.stringify([source, target]);
const validLine = line => Number.isSafeInteger(line) && line > 0;

function evidence(candidate, locations) {
  const unique = new Map();
  for (const location of locations) {
    if (typeof location.path !== "string" || !validLine(location.line)) continue;
    const key = JSON.stringify([location.path, location.line]);
    if (!unique.has(key)) unique.set(key, { path: location.path, line: location.line, label: location.label });
  }
  const values = [...unique.values()];
  return { ...candidate, evidence: values.slice(0, MAX_EVIDENCE),
    omitted_evidence: Math.max(0, values.length - MAX_EVIDENCE) };
}

function observedNode(item) {
  return { id: item.id, label: item.path, detail: item.detail || "확인한 Python 파일",
    path: item.path, line: item.line || 1, proposed: false };
}

function separateRoles(selected, routes, tables) {
  const locations = items => items.map(item => ({ path: selected.path, line: item.line, label: item.label }));
  const proposedImport = { source: ROUTE_ROLE, target: TABLE_ROLE,
    label: "실제 모델 참조가 필요할 때 import 추가 검토", proposed: true };
  return evidence({ id: "separate-roles", title: "라우트·테이블 역할 분리 검토",
    observation: `같은 파일에 표시된 라우트 ${routes.length}개와 테이블 ${tables.length}개의 직접 선언이 있습니다.`,
    why: "핸들러와 테이블을 서로 다른 목적으로 변경하거나 재사용해야 한다면 역할을 나누는 대안을 검토할 수 있습니다.",
    assumptions: [
      "같은 파일에 있다는 사실만으로 라우트가 해당 테이블을 실제로 사용한다고 확정하지 않습니다. 원본의 사용 지점을 먼저 확인해야 합니다.",
      "제안의 두 상자는 담당 역할이며 실제로 존재하는 새 파일이 아닙니다. 파일 이름·공유 선언의 소유 위치는 아직 정하지 않았습니다.",
      "모델을 실제로 참조해야 하는 경우에만 제안한 import가 필요합니다. 라우터 등록과 기존 import 경로를 보존할 수 있어야 합니다.",
    ],
    actions: [
      "테이블과 핸들러에서 공유하는 타입·설정·함수의 사용 지점을 읽고, 유지할 공개 계약과 각 선언의 소유 위치를 정하세요.",
      "테이블 선언을 별도 역할로 옮기는 변경안을 작성하고, 실제로 필요한 import와 모든 기존 사용처를 함께 조정하세요.",
      "라우터 등록·모델 메타데이터·마이그레이션 참조가 유지되는지 확인한 뒤 PR 비교로 실제 변경 범위를 검토하세요.",
    ],
    checks: [
      "앱 시작과 라우터 등록, 입력·응답 계약의 회귀 검사를 실제로 실행하세요.",
      "테이블 이름·메타데이터·기존 데이터와의 호환성 및 마이그레이션 생성 결과를 별도로 확인하세요.",
      "새 import가 역방향 참조나 다른 순환을 만들지 않는지 전체 범위를 다시 분석하세요.",
    ],
    tradeoffs: [
      "파일·import 경로와 유지할 공개 계약이 늘 수 있습니다. 선언을 복제해서 두 곳에서 관리하지 않도록 해야 합니다.",
      "작은 예제나 함께 변경되는 코드에서는 분리의 이점이 작을 수 있습니다. 현재 구조를 유지하는 선택도 검토하세요.",
    ],
    before: { nodes: [{ ...observedNode(selected), detail: `표시된 라우트 ${routes.length}개 · 테이블 ${tables.length}개` }], edges: [] },
    after: { nodes: [
      { id: ROUTE_ROLE, label: "라우트 담당 역할", detail: `라우트 ${routes.length}개 · 분리 후보, 파일명 미정`, proposed: true },
      { id: TABLE_ROLE, label: "테이블 담당 역할", detail: `테이블 ${tables.length}개 · 분리 후보, 파일명 미정`, proposed: true },
    ], edges: [proposedImport] },
    changes: [{ status: "add", source: ROUTE_ROLE, target: TABLE_ROLE, label: proposedImport.label }],
  }, [...locations(routes.slice(0, 1)), ...locations(tables.slice(0, 1)),
    ...locations(routes.slice(1)), ...locations(tables.slice(1))]);
}

function importPairs(report, nodes) {
  const pairs = new Map();
  for (const edge of report.edges) {
    const source = nodes.get(edge.source);
    if (!source || !nodes.has(edge.target) || edge.source === edge.target
        || edge.evidence?.path !== source.path || !validLine(edge.evidence?.line)) continue;
    const key = pairKey(edge.source, edge.target);
    if (!pairs.has(key)) pairs.set(key, { source: edge.source, target: edge.target, locations: [] });
    pairs.get(key).locations.push({ ...edge.evidence, label: edge.label });
  }
  for (const pair of pairs.values()) pair.locations.sort((a, b) => a.line - b.line || compare(a.label || "", b.label || ""));
  return pairs;
}

function shortestCycle(id, pairs) {
  const adjacency = new Map();
  for (const pair of pairs.values()) {
    if (!adjacency.has(pair.source)) adjacency.set(pair.source, []);
    adjacency.get(pair.source).push(pair.target);
  }
  for (const neighbors of adjacency.values()) neighbors.sort(compare);
  const queue = [[id]], visited = new Set([id]);
  for (let index = 0; index < queue.length; index++) {
    const path = queue[index];
    for (const target of adjacency.get(path[path.length - 1]) || []) {
      if (target === id && path.length > 1) return path;
      if (!visited.has(target)) {
        visited.add(target);
        queue.push([...path, target]);
      }
    }
  }
  return null;
}

function breakCycle(path, pairs, nodes) {
  const cyclePairs = path.map((source, index) => pairs.get(pairKey(source, path[(index + 1) % path.length])));
  const edges = cyclePairs.map(pair => ({ source: pair.source, target: pair.target, label: "직접 import", proposed: false }));
  const first = cyclePairs[0];
  const graphNodes = path.map(id => observedNode(nodes.get(id)));
  return evidence({ id: "break-cycle", title: "순환 경로의 참조 방향 조정 검토",
    observation: `선택 파일로 돌아오는 직접 import 경로에 파일 ${path.length}개가 있습니다. 여러 import는 파일 쌍 기준으로 묶어 표시합니다.`,
    why: "서로 참조하는 계약을 함께 바꿔야 하는지 확인하고, 한 방향의 의존을 조정하는 대안을 비교할 수 있습니다.",
    assumptions: [
      "관찰한 것은 정적인 직접 import 경로입니다. 실행 중 순환 오류나 앱 시작 실패가 발생했다는 판정은 아닙니다.",
      `${first.source} → ${first.target}의 모든 사용 이름과 사용 지점을 확인하고, 필요한 동작을 다른 계약·소유 위치 또는 호출 방향으로 보존할 수 있어야 합니다.`,
      "제안은 이 파일 쌍의 참조를 조정한 가정입니다. import문을 바로 삭제할 수 있다거나 전체 순환이 해결된다는 뜻은 아닙니다.",
    ],
    actions: [
      "제거 후보 관계의 모든 import와 실제 사용 지점을 읽고, 양쪽이 공유하는 선언과 각 선언의 소유 위치를 정하세요.",
      "필요한 공유 계약을 적절한 위치로 옮기거나 호출 방향을 조정하는 변경안을 작성하세요. 선언 복제나 단순 import 삭제로 대체하지 마세요.",
      "관련 사용처를 함께 수정한 뒤 이 방향의 직접 참조가 남지 않는지 확인하고 전체 그래프를 다시 분석하세요.",
    ],
    checks: [
      "앱 시작·모듈 로딩과 관련 입력·반환값의 회귀 검사를 실제로 실행하세요.",
      "공개 import 경로·라우터 등록·모델 메타데이터를 사용하는 코드가 같은 계약을 유지하는지 확인하세요.",
      "다른 순환 경로와 미확인 import를 별도로 확인하세요. 제안에서 경로 하나가 끊겨 보이는 것만으로 전체 문제가 해결됐다고 판단하지 마세요.",
    ],
    tradeoffs: [
      "공유 계약을 옮기면 파일 수와 공개 import 경로·유지할 계약이 늘 수 있습니다.",
      "순환 경로가 실제 동작에 문제를 만들지 않을 수도 있습니다. 변경 비용과 독립적으로 수정·검증할 필요를 비교하세요.",
    ],
    before: { nodes: graphNodes, edges },
    after: { nodes: graphNodes.map(item => ({ ...item })), edges: edges.slice(1).map(item => ({ ...item })) },
    changes: [{ status: "remove", source: first.source, target: first.target,
      label: "공유 계약·사용 지점·참조 방향을 조정한 뒤 제거 검토" }],
  }, [...cyclePairs.map(pair => pair.locations[0]), ...cyclePairs.flatMap(pair => pair.locations.slice(1))]);
}

export function repositoryProposals(report, id) {
  const review = repositoryReview(report, id);
  const selected = report.nodes.find(item => item.id === id);
  const result = { selected_path: selected?.path || null, candidates: [], coverage: review.coverage,
    limits: [...review.limits, "제안 구조는 아직 적용·실행·검증하지 않은 조건부 변경안입니다. 실제 파일·관계·성능 개선이 확인된 결과가 아닙니다."],
    empty_reason: "표시한 근거에서 이 파일에 적용할 역할 분리·순환 참조 조정 후보를 찾지 못했습니다. 구조가 안전하거나 개선이 불필요하다는 판정은 아닙니다." };
  if (!selected) {
    result.empty_reason = "선택 파일을 찾을 수 없습니다. 표시된 파일에서 다시 선택하세요.";
    return result;
  }
  const declarations = (selected.declarations || []).filter(item => validLine(item.line));
  const routes = declarations.filter(item => item.kind === "route");
  const tables = declarations.filter(item => item.kind === "model");
  if (routes.length && tables.length) result.candidates.push(separateRoles(selected, routes, tables));
  const nodes = new Map(report.nodes.map(item => [item.id, item]));
  const pairs = importPairs(report, nodes);
  const path = shortestCycle(id, pairs);
  if (path && path.length <= MAX_CYCLE_NODES) result.candidates.push(breakCycle(path, pairs, nodes));
  else if (path) {
    const note = `선택 파일로 돌아오는 최단 직접 import 경로는 파일 ${path.length}개입니다. 비교 도표의 파일 ${MAX_CYCLE_NODES}개 한도로 이 후보는 생략했으며 일부 경로만 순환처럼 그리지 않습니다.`;
    result.limits.push(note);
    if (!result.candidates.length) result.empty_reason = note;
  }
  return result;
}

const oneLine = value => String(value).replace(/[\r\n]+/g, " ");

export function repositoryProposalText(snapshot, result, candidateId) {
  const candidate = result.candidates.find(item => item.id === candidateId);
  const lines = ["저장소 구조 개선 후보 비교 — 미적용 가정", `저장소: ${oneLine(snapshot.repo)}`,
    `커밋: ${oneLine(snapshot.head)}`, `Python 소스 루트: ${oneLine(snapshot.root)}`,
    `선택 파일: ${oneLine(result.selected_path || "미선택")}`];
  if (result.coverage) lines.push(`범위: Python 원본 ${snapshot.totalFiles}개 중 구문 분석 ${result.coverage.parsed_files}개, 그래프 파일 ${result.coverage.displayed_files}개·관계 ${result.coverage.displayed_edges}개 표시`);
  if (candidate) {
    const labels = new Map([...candidate.before.nodes, ...candidate.after.nodes].map(item => [item.id, item.label]));
    lines.push("", `후보: ${candidate.title}`, `관찰: ${oneLine(candidate.observation)}`, `검토 이유: ${oneLine(candidate.why)}`);
    for (const [title, graph] of [["현재 구조 — 관찰한 범위", candidate.before], ["제안 구조 — 조건 충족 후의 가정", candidate.after]]) {
      lines.push("", title);
      for (const item of graph.nodes) lines.push(`구성요소: ${oneLine(item.label)} · ${oneLine(item.detail)}${item.proposed ? " · 제안 역할, 실제 파일 미정" : ""}`);
      if (!graph.edges.length) lines.push("이 비교에서 그린 관계 없음. 전체 관계가 없다는 판정은 아님.");
      for (const edge of graph.edges) lines.push(`관계: ${oneLine(labels.get(edge.source))} → ${oneLine(labels.get(edge.target))} · ${oneLine(edge.label)}${edge.proposed ? " · 추가 검토 가정" : ""}`);
    }
    lines.push("", "변경할 관계 후보");
    for (const change of candidate.changes) lines.push(`${change.status === "remove" ? "제거 검토" : "추가 검토"}: ${oneLine(labels.get(change.source))} → ${oneLine(labels.get(change.target))} · ${oneLine(change.label)}`);
    for (const [title, items] of [["전제", candidate.assumptions], ["다음 행동", candidate.actions], ["검증할 사항", candidate.checks], ["비용과 대안", candidate.tradeoffs]]) {
      lines.push("", title, ...items.map(oneLine));
    }
    lines.push("", "현재 코드 근거");
    for (const item of candidate.evidence) lines.push(`${oneLine(item.label)} (${oneLine(item.path)}:${item.line})`, sourceURL(snapshot.repo, snapshot.head, item.path, item.line));
    if (candidate.omitted_evidence) lines.push(`근거 ${candidate.omitted_evidence}곳은 목록 한도로 생략했습니다.`);
  } else lines.push("", candidateId ? "선택한 개선 후보를 찾을 수 없습니다. 표시된 후보에서 다시 선택하세요." : oneLine(result.empty_reason));
  lines.push("", "한도와 미확인 범위", ...result.limits.map(oneLine), ...(snapshot.warnings || []).map(oneLine));
  return lines.join("\n");
}
