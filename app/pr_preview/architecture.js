import { sourceURL } from "./github.js";

const labels = { file: "파일", route: "라우트 선언", model: "테이블·지정 DB 모델", response: "데이터·응답 모델" };
const statuses = { added: "선언 추가", removed: "선언 삭제", modified: "선언 수정", unchanged: "동일" };
const colors = { added: "#087548", removed: "#ae343f", modified: "#8a5900", unchanged: "#53627a" };
const namespace = "http://www.w3.org/2000/svg";

function element(tag, text, className) {
  const value = document.createElement(tag);
  if (text !== undefined) value.textContent = text;
  if (className) value.className = className;
  return value;
}

function svgElement(tag, attributes = {}, text) {
  const value = document.createElementNS(namespace, tag);
  for (const [name, content] of Object.entries(attributes)) value.setAttribute(name, content);
  if (text !== undefined) value.textContent = text;
  return value;
}

function shortened(text, length) {
  return text.length > length ? text.slice(0, length - 1) + "…" : text;
}

export function componentSource(pull, component, side) {
  const file = pull.files.find(file => file.path === component.path);
  return sourceURL(side === "before" ? pull.baseRepo : pull.headRepo,
    side === "before" ? pull.base : pull.head,
    side === "before" ? file?.previous_path || component.path : component.path, component.line);
}

export function downloadSVG(currentSVG, filename) {
  const svg = currentSVG.cloneNode(true);
  for (const anchor of svg.querySelectorAll("a")) anchor.removeAttribute("href");
  const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(svg)], { type: "image/svg+xml;charset=utf-8" }));
  const anchor = element("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// These are review suggestions from observed declarations, not a runtime diagnosis.
export function structureSuggestions(report) {
  const suggestions = [];
  const graphs = [report.structure?.before, report.structure?.after].filter(Boolean);
  const components = graphs.flatMap(graph => graph.nodes).filter(node => node.kind !== "file");
  const changed = components.filter(node => node.status !== "unchanged");
  const routes = [...new Set(changed.filter(node => node.kind === "route").map(node => node.label || "라우트 선언"))];
  if (routes.length) {
    suggestions.push({
      title: "API 계약 테스트를 함께 확인하세요",
      reason: "변경된 라우트·핸들러: " + routes.slice(0, 3).join(", ") + (routes.length > 3 ? ` 외 ${routes.length - 3}개` : ""),
      action: "수정한 메서드·경로의 요청, 응답 형식과 권한 테스트를 확인하세요. 도표의 라우트에서 코드를 열 수 있습니다.",
    });
  }
  if (report.models.length || report.migrations.length) {
    const evidence = [...report.models, ...report.migrations].filter(entry => !entry.startsWith("  "));
    suggestions.push({
      title: "DB 변경과 배포 순서를 함께 검토하세요",
      reason: "확인한 변경 근거: " + evidence.slice(0, 2).map(entry => shortened(entry.split(" · ").slice(0, 3).join(" · "), 120)).join("; ")
        + (evidence.length > 2 ? ` 외 ${evidence.length - 2}개` : ""),
      action: "기존 데이터의 길이·NULL·기본값과 마이그레이션 적용 순서를 확인하세요. 선언만으로 실제 DB의 호환성을 판정할 수는 없습니다.",
    });
  }
  if (components.some(node => node.kind === "route") && components.some(node => node.kind === "model")) {
    suggestions.push({
      title: "API와 DB 사이의 실제 연결을 확인하세요",
      reason: "읽은 파일에 라우트와 DB 모델이 모두 있지만 호출·데이터 접근 관계는 분석하지 않았습니다.",
      action: "핸들러의 서비스·저장소 호출과 모델 사용 지점을 확인한 뒤 시스템 구성도로 확장하세요.",
    });
  }
  if (!suggestions.length) suggestions.push({
    title: "읽은 범위를 먼저 확인하세요",
    reason: "지원하는 선언에서 구체적인 변경 검토 항목을 도출하지 못했습니다.",
    action: "아래 변경 파일과 추가 확인 항목을 확인하세요. 변경이 없거나 시스템이 안전하다는 판정은 아닙니다.",
  });
  return suggestions;
}

function diagram(graph, pull, side) {
  const files = graph.nodes.filter(node => node.kind === "file");
  const children = new Map(files.map(file => [file.id, []]));
  const nodes = new Map(graph.nodes.map(node => [node.id, node]));
  for (const edge of graph.edges) {
    if (edge.kind === "defines" && children.has(edge.source) && nodes.has(edge.target)) {
      children.get(edge.source).push(nodes.get(edge.target));
    }
  }
  const height = files.reduce((sum, file) => sum + Math.max(84, children.get(file.id).length * 80) + 32, 86);
  const svg = svgElement("svg", { xmlns: namespace, viewBox: `0 0 640 ${height}`, width: 640,
    height, role: "img", "aria-label": (side === "before" ? "이전" : "이후") + " 커밋의 PR 관련 코드 구조" });
  svg.append(svgElement("title", {}, "파일과 직접 선언한 라우트·모델의 관계"));
  svg.append(svgElement("desc", {}, "왼쪽 파일과 오른쪽 선언을 선으로 연결합니다. 실제 호출이나 네트워크 연결을 뜻하지 않습니다. 아래 구성요소 목록에서도 같은 코드를 열 수 있습니다."));
  svg.append(svgElement("rect", { width: 640, height, fill: "#f7f9fc" }));
  svg.append(svgElement("text", { x: 20, y: 24, fill: "#203451", "font-size": 14, "font-family": "system-ui, sans-serif" },
    shortened(pull.repo, 45) + ` #${pull.number} · ${side === "before" ? "이전" : "이후"} ${(side === "before" ? pull.base : pull.head).slice(0, 7)}`));
  svg.append(svgElement("text", { x: 20, y: 47, fill: "#53627a", "font-size": 14, "font-family": "system-ui, sans-serif" },
    "PR 변경 파일의 직접 선언 · 상속·호출·DB 접근·운영 인프라 미확인"));

  function card(component, x, y, width) {
    const color = colors[component.status] || colors.unchanged;
    const anchor = svgElement("a", { href: componentSource(pull, component, side), target: "_blank", rel: "noopener noreferrer" });
    anchor.append(svgElement("title", {}, `${component.label}\n${component.detail}\n${statuses[component.status]} · ${component.path}:${component.line}`));
    anchor.append(svgElement("rect", { x, y, width, height: 68, rx: 8, fill: "#fff", stroke: color, "stroke-width": 1.5 }));
    anchor.append(svgElement("text", { x: x + 13, y: y + 21, fill: color, "font-size": 14, "font-family": "system-ui, sans-serif" }, `${labels[component.kind]} · ${statuses[component.status]}`));
    const label = svgElement("svg", { x: x + 13, y: y + 26, width: width - 26, height: 29 });
    label.append(svgElement("text", { x: 0, y: 19, fill: "#203451", "font-size": 15, "font-weight": 600, "font-family": "system-ui, sans-serif" }, shortened(component.label, width === 200 ? 21 : 34)));
    anchor.append(label);
    svg.append(anchor);
  }
  let top = 70;
  for (const file of files) {
    const declarations = children.get(file.id);
    const groupHeight = Math.max(84, declarations.length * 80);
    const fileTop = top + 8;
    for (const [index, component] of declarations.entries()) {
      const childTop = top + index * 80;
      svg.append(svgElement("path", { d: `M 220 ${fileTop + 34} H 240 V ${childTop + 34} H 260`,
        fill: "none", stroke: "#9cabc2", "stroke-width": 1.5 }));
      card(component, 260, childTop, 360);
    }
    card(file, 20, fileTop, 200);
    top += groupHeight + 32;
  }
  return svg;
}

export function architectureSection(pull, report) {
  const section = element("section", undefined, "result-section architecture-section");
  section.append(element("h3", "PR 관련 코드 구조"));
  section.append(element("p", "선택한 PR 변경 파일의 구조입니다. 선은 파일이 라우트·모델을 선언한다는 뜻입니다. 전체 저장소, 실제 호출·DB 접근·운영 인프라는 포함하지 않습니다.", "help"));
  section.append(element("p", "도표는 좌우·아래로 스크롤할 수 있습니다. 구성요소를 누르면 해당 커밋의 코드가 열립니다.", "help"));
  if (!report.structure) {
    section.append(element("p", "코드 구조 정보를 읽지 못했습니다. 변경 근거를 확인해 주세요.", "empty"));
    return section;
  }
  const controls = element("div", undefined, "report-actions structure-controls");
  const before = element("button", "이전 구조");
  const after = element("button", "이후 구조");
  const save = element("button", "SVG 저장");
  for (const button of [before, after, save]) button.type = "button";
  controls.append(before, after, save);
  const body = element("div");
  section.append(controls, body);
  let selected = "after";
  let currentSVG;
  function show(side) {
    selected = side;
    before.setAttribute("aria-pressed", String(side === "before"));
    after.setAttribute("aria-pressed", String(side === "after"));
    const graph = report.structure[side];
    body.replaceChildren();
    const commit = side === "before" ? pull.base : pull.head;
    body.append(element("p", (side === "before" ? "이전" : "이후") + " " + commit.slice(0, 7) + " · " + graph.nodes.length + "개 구성요소 표시 · 추가 / 수정 / 삭제 / 동일은 직접 선언만 비교. ‘동일’도 상속·간접 영향은 별도 확인", "structure-meta"));
    currentSVG = null;
    save.disabled = !graph.nodes.length;
    if (graph.nodes.length) {
      const viewport = element("div", undefined, "structure-viewport");
      viewport.tabIndex = 0;
      viewport.setAttribute("role", "region");
      viewport.setAttribute("aria-label", "코드 구조도. 좁은 화면에서는 가로로 스크롤할 수 있습니다.");
      currentSVG = diagram(graph, pull, side);
      viewport.append(currentSVG);
      body.append(viewport);
      const details = element("details", undefined, "structure-list");
      details.append(element("summary", "구성요소와 코드 근거 목록"));
      const list = element("ul", undefined, "review-list");
      for (const component of graph.nodes) {
        const item = element("li");
        const source = element("a", component.label, "source-link");
        source.href = componentSource(pull, component, side);
        source.target = "_blank";
        source.rel = "noopener noreferrer";
        item.append(source, element("p", `${labels[component.kind]} · ${statuses[component.status]} · ${component.detail} · ${component.path}:${component.line}`));
        list.append(item);
      }
      details.append(list);
      body.append(details);
    } else body.append(element("p", "이 커밋의 읽은 범위에 표시할 Python 코드 구조가 없습니다. 추가·삭제 여부와 읽지 못한 파일을 함께 확인하세요.", "empty"));
    if (graph.omitted_nodes) body.append(element("p", `표시 한도 때문에 구성요소 ${graph.omitted_nodes}개를 생략했습니다. 경로 범위를 좁혀 확인하세요.`, "coverage-note"));
    if (report.structure.unreadable_paths.length) body.append(element("p", "이전·이후 소스를 모두 읽지 못해 구조도에서 제외: " + report.structure.unreadable_paths.join(", "), "coverage-note"));
    if (report.structure.uncertain_route_paths?.length) body.append(element("p", "경로·바인딩 등을 확정하지 못한 라우트는 양쪽 구조 비교에서 제외했습니다. 추가·삭제로 판단하지 않았습니다: " + report.structure.uncertain_route_paths.join(", ") + ". 아래 변경 파일의 추가 확인 항목을 보세요.", "coverage-note"));
  }
  before.addEventListener("click", () => show("before"));
  after.addEventListener("click", () => show("after"));
  save.addEventListener("click", () => {
    if (!currentSVG) return;
    downloadSVG(currentSVG, `pr-${pull.number}-${selected}-structure.svg`);
  });
  show(selected);
  const suggestions = element("section", undefined, "structure-suggestions");
  suggestions.append(element("h4", "구조를 바탕으로 한 검토 제안"));
  const list = element("ul", undefined, "evidence-list");
  for (const suggestion of structureSuggestions(report)) {
    const item = element("li", undefined, "evidence-item");
    item.append(element("strong", suggestion.title), element("p", "근거: " + suggestion.reason), element("p", suggestion.action));
    list.append(item);
  }
  suggestions.append(list);
  section.append(suggestions);
  return section;
}
