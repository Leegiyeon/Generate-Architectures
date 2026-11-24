import { sourceURL } from "./github.js";
import { downloadSVG } from "./architecture.js";
import { repositoryReview, repositoryReviewText } from "./repository-review.js";
import { repositoryProposals, repositoryProposalText } from "./repository-proposals.js";
import { copyOutput } from "./copy-output.js";
import { repositoryURL } from "./review-link.js";

const namespace = "http://www.w3.org/2000/svg";
const MAX_NEIGHBORS = 12;

function node(tag, text, className) {
  const value = document.createElement(tag);
  if (text !== undefined) value.textContent = text;
  if (className) value.className = className;
  return value;
}

function source(snapshot, path, line, text) {
  const anchor = node("a", text || path, "source-link");
  anchor.href = sourceURL(snapshot.repo, snapshot.head, path, line);
  anchor.target = "_blank";
  anchor.rel = "noopener noreferrer";
  return anchor;
}

function svgNode(tag, attributes = {}, text) {
  const value = document.createElementNS(namespace, tag);
  for (const [key, content] of Object.entries(attributes)) value.setAttribute(key, content);
  if (text !== undefined) value.textContent = text;
  return value;
}

function short(text, length) { return text.length > length ? text.slice(0, length - 1) + "…" : text; }

function reviewSection(snapshot, review) {
  const section = node("section", undefined, "result-section repository-plan");
  section.append(node("h3", "목적별 검토 계획 · " + review.title));
  section.append(node("p", review.summary, "help"));
  const list = node("ol", undefined, "evidence-list");
  for (const step of review.steps) {
    const item = node("li", undefined, "evidence-item");
    item.append(node("h4", step.title));
    for (const [label, value] of [["현재 확인", step.observation], ["다음 행동", step.action], ["완료 조건", step.check]]) {
      const paragraph = node("p");
      paragraph.append(node("strong", label + " · "), document.createTextNode(value));
      item.append(paragraph);
    }
    const evidence = node("details", undefined, "structure-list");
    evidence.append(node("summary", `코드 근거 ${step.evidence.length}곳${step.omitted_evidence ? ` · ${step.omitted_evidence}곳 더 생략` : ""}`));
    const sources = node("ul", undefined, "review-list");
    for (const location of step.evidence) {
      const entry = node("li");
      entry.append(source(snapshot, location.path, location.line, `${location.path}:${location.line}`));
      if (location.label) entry.append(node("p", location.label));
      sources.append(entry);
    }
    evidence.append(sources);
    item.append(evidence);
    list.append(item);
  }
  section.append(list);
  if (review.limits.length) {
    const limits = node("ul", undefined, "review-list repository-plan-limits");
    for (const limit of review.limits) limits.append(node("li", limit));
    section.append(limits);
  }
  section.append(copyOutput({
    label: "검토 계획 복사",
    getText: () => repositoryReviewText(snapshot, review),
    successMessage: "커밋·소스 루트·코드 근거와 확인 범위를 포함한 검토 계획을 복사했습니다.",
    fallbackLabel: "복사할 검토 계획",
  }));
  return section;
}

export function repositoryFocus(report, id, direction = "outgoing") {
  const selected = report.nodes.find(item => item.id === id);
  if (!selected) return { selected: null, neighbors: [], edges: [], omitted_neighbors: 0 };
  const edges = report.edges.filter(edge => direction === "incoming" ? edge.target === id : edge.source === id);
  const ids = new Set(edges.map(edge => direction === "incoming" ? edge.source : edge.target));
  const neighbors = report.nodes.filter(item => ids.has(item.id)).sort((a, b) => a.path.localeCompare(b.path));
  return { selected, neighbors: neighbors.slice(0, MAX_NEIGHBORS), edges,
    omitted_neighbors: Math.max(0, neighbors.length - MAX_NEIGHBORS) };
}

export function defaultRepositoryFile(report, path) {
  return report.nodes.find(item => item.path === path)?.id
    || report.nodes.find(item => item.declarations?.some(declaration => declaration.kind === "route"))?.id
    || report.nodes.find(item => report.edges.some(edge => edge.source === item.id))?.id
    || report.nodes[0]?.id;
}

function diagram(snapshot, focus, direction) {
  const height = Math.max(190, 100 + focus.neighbors.length * 84);
  const svg = svgNode("svg", { xmlns: namespace, viewBox: `0 0 640 ${height}`, width: 640, height,
    role: "img", "aria-label": "선택 파일의 직접 import 선언 대상" });
  svg.append(svgNode("title", {}, "고정 커밋에서 확인한 import 선언"));
  svg.append(svgNode("desc", {}, "왼쪽은 선택 파일, 오른쪽은 표시한 import 관계의 이웃 파일입니다. 화살표는 import 방향이며 실제 함수 호출이나 실행 여부를 뜻하지 않습니다. 아래에 같은 관계의 코드 근거 목록이 있습니다."));
  svg.append(svgNode("rect", { width: 640, height, fill: "#f7f9fc" }));
  svg.append(svgNode("text", { x: 18, y: 24, fill: "#203451", "font-size": 14 }, short(snapshot.repo, 47) + " · " + snapshot.head.slice(0, 7)));
  svg.append(svgNode("text", { x: 18, y: 47, fill: "#53627a", "font-size": 14 },
    `루트 ${short(snapshot.root, 18)} · ${direction === "incoming" ? "선택 파일을 참조" : "선택 파일이 참조"} · 이웃 ${focus.neighbors.length}개 표시`));
  const definitions = svgNode("defs");
  const marker = svgNode("marker", { id: "repository-arrow", viewBox: "0 0 10 10", refX: 9, refY: 5,
    markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" });
  marker.append(svgNode("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "#7c90ae" }));
  definitions.append(marker);
  svg.append(definitions);
  function card(item, x, y, selected = false) {
    const anchor = svgNode("a", { href: sourceURL(snapshot.repo, snapshot.head, item.path, 1), target: "_blank", rel: "noopener noreferrer" });
    anchor.append(svgNode("title", {}, item.path + "\n" + item.detail));
    anchor.append(svgNode("rect", { x, y, width: 250, height: 65, rx: 8, fill: "#fff", stroke: selected ? "#2556d9" : "#a7b6cb", "stroke-width": 1.5 }));
    const label = svgNode("svg", { x: x + 12, y: y + 9, width: 226, height: 50 });
    label.append(svgNode("text", { x: 0, y: 18, fill: "#203451", "font-size": 14, "font-family": "system-ui, sans-serif" }, short(item.path, 26)));
    label.append(svgNode("text", { x: 0, y: 40, fill: "#53627a", "font-size": 14, "font-family": "system-ui, sans-serif" }, short(item.detail, 26)));
    anchor.append(label);
    svg.append(anchor);
  }
  for (const [index, item] of focus.neighbors.entries()) {
    const y = 76 + index * 84;
    const path = direction === "incoming" ? `M 370 ${y + 32} H 322 V 108 H 270` : `M 270 108 H 322 V ${y + 32} H 370`;
    svg.append(svgNode("path", { d: path, fill: "none", stroke: "#7c90ae", "stroke-width": 1.5, "marker-end": "url(#repository-arrow)" }));
    card(item, 370, y);
  }
  card(focus.selected, 20, 76, true);
  return svg;
}

function comparisonDiagram(snapshot, candidate) {
  const height = 150 + Math.max(candidate.before.nodes.length, candidate.after.nodes.length) * 92;
  const svg = svgNode("svg", { xmlns: namespace, viewBox: `0 0 960 ${height}`, width: 960, height,
    role: "img", "aria-label": "현재 구조와 조건부 개선 후보 비교" });
  svg.append(svgNode("title", {}, candidate.title));
  svg.append(svgNode("desc", {}, "왼쪽은 관찰한 현재 구조의 일부이고 오른쪽은 코드에 적용하지 않은 가정입니다. 점선은 제안한 역할이나 관계이며 아래에 같은 내용의 텍스트·전제·코드 근거가 있습니다."));
  svg.append(svgNode("metadata", {}, JSON.stringify({ repo: snapshot.repo, commit: snapshot.head,
    root: snapshot.root, candidate: candidate.id, state: "hypothetical-not-applied" })));
  svg.append(svgNode("rect", { width: 960, height, fill: "#f7f9fc" }));
  svg.append(svgNode("text", { x: 20, y: 25, fill: "#203451", "font-size": 14 },
    short(snapshot.repo, 48) + " · " + snapshot.head.slice(0, 7) + " · 루트 " + short(snapshot.root, 30)));
  const defs = svgNode("defs");
  for (const [name, color] of [["observed", "#7c90ae"], ["proposed", "#966519"]]) {
    const marker = svgNode("marker", { id: "proposal-arrow-" + name, viewBox: "0 0 10 10", refX: 9, refY: 5,
      markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" });
    marker.append(svgNode("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: color }));
    defs.append(marker);
  }
  svg.append(defs);
  for (const [index, graph] of [candidate.before, candidate.after].entries()) {
    const x = 20 + index * 480;
    svg.append(svgNode("text", { x, y: 65, fill: "#203451", "font-size": 16, "font-weight": 650 }, index ? "개선 후보 · 가정 / 미적용" : "현재 · 관찰한 범위"));
    const positions = new Map(graph.nodes.map((item, row) => [item.id, 92 + row * 92]));
    for (const [edgeIndex, edge] of graph.edges.entries()) {
      const start = positions.get(edge.source) + 32;
      const end = positions.get(edge.target) + 32;
      const rail = x + 370 + edgeIndex * 9;
      const path = svgNode("path", { d: `M ${x + 340} ${start} H ${rail} V ${end} H ${x + 340}`,
        fill: "none", stroke: edge.proposed ? "#966519" : "#7c90ae", "stroke-width": 1.6,
        "marker-end": `url(#proposal-arrow-${edge.proposed ? "proposed" : "observed"})` });
      if (edge.proposed) path.setAttribute("stroke-dasharray", "6 4");
      path.append(svgNode("title", {}, edge.label));
      svg.append(path);
    }
    for (const item of graph.nodes) {
      const y = positions.get(item.id);
      const card = item.path && !item.proposed
        ? svgNode("a", { href: sourceURL(snapshot.repo, snapshot.head, item.path, item.line || 1), target: "_blank", rel: "noopener noreferrer" })
        : svgNode("g");
      card.append(svgNode("title", {}, item.label + "\n" + item.detail));
      const rectangle = svgNode("rect", { x, y, width: 340, height: 65, rx: 8, fill: "#fff",
        stroke: item.proposed ? "#966519" : "#7c90ae", "stroke-width": 1.5 });
      if (item.proposed) rectangle.setAttribute("stroke-dasharray", "6 4");
      card.append(rectangle);
      card.append(svgNode("text", { x: x + 12, y: y + 26, fill: "#203451", "font-size": 14 }, short(item.label, 37)));
      card.append(svgNode("text", { x: x + 12, y: y + 49, fill: "#53627a", "font-size": 14 }, short(item.detail, 37)));
      svg.append(card);
    }
  }
  svg.append(svgNode("text", { x: 20, y: height - 18, fill: "#53627a", "font-size": 14 }, "점선: 제안 역할·관계. 선택 파일의 선언 또는 순환 경로만 비교합니다."));
  return svg;
}

function proposalSection(snapshot, report, id) {
  const result = repositoryProposals(report, id);
  const section = node("details", undefined, "result-section repository-proposals");
  section.id = "repository-proposals";
  section.append(node("summary", `구조 개선 후보 비교 · ${result.candidates.length}개`));
  if (!result.candidates.length) {
    section.append(node("p", result.empty_reason, "empty"));
    for (const limit of result.limits) section.append(node("p", limit, "help"));
    return section;
  }
  section.open = true;
  const select = node("select");
  select.id = "repository-proposal";
  for (const candidate of result.candidates) {
    const option = node("option", candidate.title);
    option.value = candidate.id;
    select.append(option);
  }
  if (result.candidates.length > 1) {
    const label = node("label", "비교할 개선 후보", "advanced-field repository-purpose");
    label.append(select);
    section.append(label);
  }
  const body = node("div");
  section.append(body);
  function show() {
    const candidate = result.candidates.find(item => item.id === select.value);
    body.replaceChildren();
    body.append(node("h3", candidate.title));
    body.append(node("p", candidate.observation, "coverage-note"), node("p", candidate.why, "help"));
    const svg = comparisonDiagram(snapshot, candidate);
    const viewport = node("div", undefined, "structure-viewport");
    viewport.tabIndex = 0;
    viewport.setAttribute("role", "region");
    viewport.setAttribute("aria-label", "현재·개선 후보 비교 도표. 좌우로 스크롤할 수 있습니다.");
    viewport.append(svg);
    body.append(viewport);
    const labels = new Map([...candidate.before.nodes, ...candidate.after.nodes].map(item => [item.id, item.label]));
    const changes = node("ul", undefined, "review-list");
    body.append(node("h4", "바꾸려는 역할·관계"));
    for (const change of candidate.changes) {
      changes.append(node("li", `${change.label} · ${labels.get(change.source) || change.source} → ${labels.get(change.target) || change.target}`));
    }
    body.append(changes);
    const context = node("details", undefined, "structure-list");
    context.append(node("summary", "전제·적용 순서·검증·단점 확인"));
    for (const [title, entries] of [["적용 전제", candidate.assumptions], ["적용 순서", candidate.actions], ["검증할 사항", candidate.checks], ["단점과 대안", candidate.tradeoffs]]) {
      context.append(node("h4", title));
      const list = node("ul", undefined, "review-list");
      for (const entry of entries) list.append(node("li", entry));
      context.append(list);
    }
    body.append(context);
    const evidence = node("details", undefined, "structure-list");
    evidence.append(node("summary", `현재 코드 근거 ${candidate.evidence.length}곳${candidate.omitted_evidence ? ` · ${candidate.omitted_evidence}곳 더 생략` : ""}`));
    const sources = node("ul", undefined, "review-list");
    for (const location of candidate.evidence) {
      const item = node("li");
      item.append(source(snapshot, location.path, location.line, `${location.path}:${location.line}`), node("p", location.label));
      sources.append(item);
    }
    evidence.append(sources);
    body.append(evidence);
    const graphText = node("details", undefined, "structure-list");
    graphText.append(node("summary", "도표의 역할·관계 텍스트"));
    for (const [title, graph] of [["현재", candidate.before], ["개선 후보 · 가정", candidate.after]]) {
      graphText.append(node("h4", title));
      const list = node("ul", undefined, "review-list");
      for (const item of graph.nodes) list.append(node("li", `${item.label} · ${item.detail}${item.proposed ? " · 제안 역할" : ""}`));
      for (const edge of graph.edges) list.append(node("li", `${labels.get(edge.source)} → ${labels.get(edge.target)} · ${edge.label}${edge.proposed ? " · 가정 관계" : ""}`));
      graphText.append(list);
    }
    body.append(graphText);
    for (const limit of result.limits) body.append(node("p", limit, "coverage-note"));
    const actions = node("div", undefined, "report-actions");
    const save = node("button", "구조 비교 SVG 저장");
    save.type = "button";
    save.addEventListener("click", () => downloadSVG(svg, `proposal-${snapshot.head.slice(0, 7)}-${candidate.id}.svg`));
    actions.append(save);
    body.append(actions);
    const exportText = node("details", undefined, "structure-list");
    exportText.append(node("summary", "구조 비교 텍스트로 보기"));
    const label = node("label", "복사할 구조 비교", "advanced-field repository-plan-copy");
    const text = node("textarea");
    text.readOnly = true;
    text.rows = 10;
    text.value = repositoryProposalText(snapshot, result, candidate.id);
    label.append(text);
    exportText.append(label);
    body.append(exportText);
  }
  select.addEventListener("change", show);
  show();
  return section;
}

export function repositoryView(snapshot, report, settings = {}, baseURL) {
  const section = node("section", undefined, "repository-result");
  const heading = node("header", undefined, "report-header");
  heading.append(node("h2", "저장소 현재 코드 구조", "report-title"));
  heading.append(node("p", snapshot.repo + " · 커밋 " + snapshot.head + " · 루트 " + snapshot.root, "report-meta"));
  if (snapshot.resolvedFrom?.branch) {
    heading.append(node("p", "기본 브랜치 " + snapshot.resolvedFrom.branch + "의 최신 커밋을 위 SHA로 고정했습니다. 다시 분석하면 최신 커밋을 확인합니다.", "help repository-limits"));
  }
  section.append(heading);
  let select, direction, purpose;
  const sharing = node("div", undefined, "copy-actions");
  function showSharing() {
    sharing.replaceChildren(copyOutput({
      label: "분석 설정 링크 복사",
      fallbackLabel: "복사할 분석 설정 링크", rows: 3,
      getText: () => repositoryURL(baseURL ?? window.location.href, {
        url: snapshot.url || "https://github.com/" + snapshot.repo,
        commit: snapshot.head, root: snapshot.root,
        file: report.nodes.find(item => item.id === select?.value)?.path || "",
        direction: direction?.value || "outgoing", purpose: purpose?.value || "onboarding",
      }),
      successMessage: "저장소·고정 커밋·루트·파일·참조 방향·목적을 담은 링크를 복사했습니다. 링크에서 ‘현재 구조 확인’을 누르세요.",
    }));
  }
  section.append(sharing);
  section.append(node("p", `범위의 Python ${snapshot.totalFiles}개 중 ${report.parsed_files}개 구문을 읽고 파일 ${report.nodes.length}개를 표시합니다. 고정 커밋의 직접 import 선언과 라우트·테이블 선언을 확인합니다.`, "coverage-note"));
  section.append(node("p", "소스 루트를 기준으로 모듈 경로가 하나로 정해지는 관계만 연결합니다. 패키지에서 가져오는 이름의 재수출·실제 로딩, 함수 호출, 최종 라우터 등록·운영 인프라는 확인하지 않습니다.", "help repository-limits"));
  for (const warning of snapshot.warnings) section.append(node("p", warning, "coverage-note"));
  if (report.omitted_nodes || report.omitted_edges) section.append(node("p", `표시 한도 등으로 파일 ${report.omitted_nodes}개·관계 ${report.omitted_edges}개를 생략했습니다.`, "coverage-note"));
  if (report.unreadable_paths.length) section.append(node("p", "읽거나 해석하지 못한 파일: " + report.unreadable_paths.join(", "), "coverage-note"));
  if (settings.file && !report.nodes.some(item => item.path === settings.file)) {
    section.append(node("p", "공유된 파일 " + settings.file + "을 현재 분석 범위에서 표시할 수 없습니다. "
      + (report.nodes.length ? "기본 파일로 열었습니다. " : "") + "읽기 실패·표시 한도를 확인하세요.", "coverage-note"));
  }
  if (!report.nodes.length) {
    showSharing();
    section.append(node("p", "표시할 Python 파일이 없습니다. 소스 루트와 읽기 실패 안내를 확인하세요.", "empty"));
    return section;
  }
  const controls = node("div", undefined, "repository-fields");
  const fileLabel = node("label", "확인할 파일", "advanced-field");
  select = node("select");
  select.id = "repository-file";
  for (const item of report.nodes) {
    const option = node("option", item.path);
    option.value = item.id;
    select.append(option);
  }
  select.value = defaultRepositoryFile(report, settings.file);
  fileLabel.append(select);
  const goalLabel = node("label", "확인할 내용", "advanced-field");
  direction = node("select");
  direction.id = "repository-direction";
  for (const [value, text] of [["outgoing", "이 파일이 참조하는 모듈"], ["incoming", "이 파일을 참조하는 파일"]]) {
    const option = node("option", text);
    option.value = value;
    direction.append(option);
  }
  direction.value = settings.direction === "incoming" ? "incoming" : "outgoing";
  goalLabel.append(direction);
  controls.append(fileLabel, goalLabel);
  section.append(controls);
  const purposeLabel = node("label", "사용 목적", "advanced-field repository-purpose");
  purpose = node("select");
  purpose.id = "repository-purpose";
  for (const [value, text] of [["onboarding", "온보딩 · 읽을 순서"], ["change", "변경 검토 · 확인할 사용 지점"], ["testing", "테스트 계획 · 검증할 계약"]]) {
    const option = node("option", text);
    option.value = value;
    purpose.append(option);
  }
  purpose.value = ["change", "testing"].includes(settings.purpose) ? settings.purpose : "onboarding";
  purposeLabel.append(purpose);
  section.append(purposeLabel, node("p", "같은 분석 결과에서 목적에 맞는 확인 순서를 제안합니다. 목적 전환에는 추가 조회가 필요하지 않습니다.", "help"));
  const plan = node("div");
  plan.id = "repository-review";
  function showReview() {
    plan.replaceChildren(reviewSection(snapshot, repositoryReview(report, select.value, purpose.value)));
  }
  const body = node("div");
  const actions = node("div", undefined, "report-actions");
  const save = node("button", "선택 구조 SVG 저장");
  save.type = "button";
  actions.append(save);
  section.append(body, actions);
  let currentSVG;
  let proposalFile;
  let proposals;
  function show() {
    const focus = repositoryFocus(report, select.value, direction.value);
    body.replaceChildren();
    currentSVG = diagram(snapshot, focus, direction.value);
    const viewport = node("div", undefined, "structure-viewport");
    viewport.tabIndex = 0;
    viewport.setAttribute("role", "region");
    viewport.setAttribute("aria-label", "선택 파일 import 구조도. 좌우로 스크롤할 수 있습니다.");
    viewport.append(currentSVG);
    body.append(viewport);
    if (focus.omitted_neighbors) body.append(node("p", `도표에서 이웃 파일 ${focus.omitted_neighbors}개를 더 생략했습니다. 관계의 코드 근거 목록도 확인하세요.`, "coverage-note"));
    body.append(node("p", direction.value === "incoming" ? "수정할 때 아래 import문을 출발점으로 사용 지점과 관련 테스트를 확인하세요. 실행 영향이 전파된다는 판정은 아닙니다." : "아래 모듈과 직접 선언을 읽어 파일의 역할을 살펴보세요. 호출 순서나 모듈 경계를 변경해야 한다는 판정은 아닙니다.", "coverage-note"));
    if (proposalFile !== select.value) {
      proposals = proposalSection(snapshot, report, select.value);
      proposalFile = select.value;
    }
    body.append(proposals);
    showReview();
    body.append(plan);
    const links = node("section", undefined, "result-section");
    links.append(node("h3", "관계의 코드 근거"));
    const list = node("ul", undefined, "review-list");
    for (const edge of focus.edges) {
      const item = node("li");
      item.append(node("p", `${edge.source} → ${edge.target} · ${edge.label}`));
      item.append(source(snapshot, edge.evidence.path, edge.evidence.line, `${edge.evidence.path}:${edge.evidence.line}`));
      list.append(item);
    }
    links.append(focus.edges.length ? list : node("p", "표시한 범위에서 확정한 직접 import 관계가 없습니다. 아래 미확인 범위를 함께 확인하세요.", "empty"));
    body.append(links);
    const declarations = node("section", undefined, "result-section");
    declarations.append(node("h3", "선택 파일의 라우트·테이블 선언"));
    declarations.append(source(snapshot, focus.selected.path, 1, focus.selected.path));
    const declarationList = node("ul", undefined, "review-list");
    for (const item of focus.selected.declarations) {
      const entry = node("li");
      entry.append(source(snapshot, focus.selected.path, item.line, item.label), node("p", item.detail));
      declarationList.append(entry);
    }
    declarations.append(focus.selected.declarations.length ? declarationList : node("p", "지원하는 직접 라우트·테이블 선언이 없습니다.", "empty"));
    if (focus.selected.omitted_declarations) declarations.append(node("p", `선언 ${focus.selected.omitted_declarations}개는 목록 한도로 생략했습니다.`, "coverage-note"));
    body.append(declarations);
    showSharing();
  }
  select.addEventListener("change", show);
  direction.addEventListener("change", show);
  purpose.addEventListener("change", () => { showReview(); showSharing(); });
  save.addEventListener("click", () => downloadSVG(currentSVG, `repository-${snapshot.head.slice(0, 7)}-${direction.value}.svg`));
  show();
  const unknown = node("details", undefined, "structure-list");
  unknown.append(node("summary", `대상을 확정하지 못한 import ${report.unresolved.length + report.omitted_unresolved}건`));
  unknown.append(node("p", "외부 패키지·선택 범위 밖·조건부·동적 import 등이 포함됩니다. 미확인 수는 오류나 실제 실행 의존성의 개수가 아닙니다.", "help"));
  const unknownList = node("ul", undefined, "review-list");
  for (const item of report.unresolved) {
    const entry = node("li");
    entry.append(node("p", item.label + " · " + item.reason), source(snapshot, item.path, item.line, `${item.path}:${item.line}`));
    unknownList.append(entry);
  }
  unknown.append(unknownList);
  if (report.omitted_unresolved) unknown.append(node("p", `목록 한도로 ${report.omitted_unresolved}건을 더 생략했습니다.`, "help"));
  section.append(unknown);
  if (report.warnings.length) {
    const warnings = node("details", undefined, "structure-list");
    warnings.append(node("summary", `해석 한도와 추가 확인 ${report.warnings.length}건`));
    const list = node("ul", undefined, "review-list");
    for (const warning of report.warnings) list.append(node("li", warning));
    warnings.append(list);
    section.append(warnings);
  }
  return section;
}
