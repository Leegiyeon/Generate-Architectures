import { loadPull, parsePullURL, sourceURL } from "./github.js";
import { feedbackURL } from "./feedback.js";
import { reviewSettings, reviewURL } from "./review-link.js";
import { architectureSection } from "./architecture.js";
import { evidenceLocation } from "./evidence.js";
import { loadRepository } from "./repository.js";
import { repositoryView } from "./repository-view.js";
import { copyOutput } from "./copy-output.js";
import { analyze } from "./worker-client.js";

const form = document.querySelector("#review-form");
const repositoryForm = document.querySelector("#repository-form");
const results = document.querySelector("#results");
const status = document.querySelector("#status");
const errorBox = document.querySelector("#error");
const feedbackLink = document.querySelector("#feedback-link");
const cancelButton = document.querySelector("#analysis-cancel");
const cancelActions = document.querySelector("#analysis-cancel-actions");
feedbackLink.href = feedbackURL();
const exampleURL = "https://github.com/fastapi/full-stack-fastapi-template/pull/2144";
let activeController;
let lastReport;
let busy = false;

function selectMode(mode) {
  if (busy) return;
  document.querySelector(".intro h1").textContent = mode === "repository" ? "현재 코드는 어떻게 연결되나요?" : "API와 DB에서 무엇이 바뀌었나요?";
  document.querySelector(".intro p").textContent = mode === "repository" ? "저장소 링크와 Python 소스 루트를 넣고, 파일별 import와 라우트·모델 선언을 확인하세요." : "PR 링크를 넣고, 관련 코드 구조와 변경 사항을 코드 근거와 함께 확인하세요.";
  for (const name of ["pr", "repository"]) {
    document.getElementById(name + "-panel").hidden = mode !== name;
    document.getElementById("mode-" + name).setAttribute("aria-pressed", String(mode === name));
  }
  results.hidden = true;
  lastReport = null;
  errorBox.hidden = true;
  progress("");
  feedbackLink.href = feedbackURL();
}

function analysisControls() {
  return [...document.querySelectorAll("#review-form input, #review-form button, #review-form textarea, #repository-form input, #repository-form button, .analysis-modes button")];
}

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function link(text, href) {
  const element = node("a", "source-link", text);
  element.href = href;
  element.target = "_blank";
  element.rel = "noopener noreferrer";
  return element;
}

function lines(id) {
  return document.getElementById(id).value.split("\n").map(value => value.trim()).filter(Boolean);
}

function progress(message) { status.textContent = message; }

function jumpTo(element) {
  if (!element.matches("input, textarea, select, button")) element.tabIndex = -1;
  element.focus({ preventScroll: true });
  element.scrollIntoView({ block: "start" });
}

function showAnalysisError(error, signal) {
  if (signal.aborted && signal.reason?.name === "AbortError") {
    progress("분석을 취소했습니다. 입력한 설정을 유지했으니 수정하거나 다시 분석할 수 있습니다.");
    return true;
  }
  errorBox.textContent = signal.aborted
    ? "조회·분석 시간이 90초를 초과했습니다. 경로·소스 루트를 좁히거나 네트워크를 확인하고 다시 시도해 주세요."
    : error.message;
  errorBox.hidden = false;
  progress("");
  jumpTo(errorBox);
  return false;
}

function locationLink(location, pull) {
  if (!location) return null;
  const { path, line, previous } = location;
  const file = pull.files.find(item => item.path === path);
  return link((previous ? "이전 " : "") + path + " " + line + "행",
    sourceURL(previous ? pull.baseRepo : pull.headRepo, previous ? pull.base : pull.head,
      previous ? file?.previous_path || path : path, line));
}

function evidenceSection(title, entries, pull) {
  const section = node("section", "result-section");
  section.append(node("h3", "", title));
  if (!entries.length) section.append(node("p", "empty", "지원 범위에서 감지된 변경이 없습니다."));
  else {
    const list = node("ul", "evidence-list");
    for (const entry of entries) {
      const detail = entry.startsWith("  ");
      const item = node("li", detail ? "evidence-detail" : "evidence-item");
      const location = evidenceLocation(entry, pull.files);
      const source = locationLink(location, pull);
      const description = location ? entry.slice(0, location.start) + entry.slice(location.start + location.length) : entry;
      item.append(node("p", "", description.trim()));
      if (source) item.append(source);
      list.append(item);
    }
    section.append(list);
  }
  return section;
}

function render(pull, report, options) {
  results.setAttribute("aria-label", "PR 변경 분석 결과");
  const focus = form.elements.focus.value;
  feedbackLink.href = feedbackURL(pull, report, options, focus);
  const focusName = { all: "전체 리뷰", api: "API 리뷰", db: "DB 리뷰" }[focus];
  results.replaceChildren();
  const header = node("header", "report-header");
  const heading = node("div");
  heading.append(node("p", "report-meta", pull.repo + " #" + pull.number + " · " + focusName));
  heading.append(node("h2", "report-title", pull.title));
  const date = new Date(pull.fetchedAt).toLocaleTimeString("ko-KR");
  heading.append(node("p", "report-meta", pull.base.slice(0, 7) + " → " + pull.head.slice(0, 7) + " · " + date + " 조회"));
  header.append(heading, link("원본 PR 보기", pull.url));
  results.append(header);
  const scope = node("p", "coverage-note",
    "선택 범위의 변경 파일 " + report.changed_files + "개 중 Python 파일 " + report.parsed_files + " / " + report.python_files +
    "개의 구문을 읽었습니다. 자동 비교는 파일 또는 함수에서 직접 만든 라우터의 선언과 직접 선언한 모델 필드 기준입니다.");
  results.append(scope);
  for (const warning of pull.warnings) results.append(node("p", "coverage-note", warning));
  const navigation = node("nav", "report-actions result-navigation");
  navigation.setAttribute("aria-label", "결과 바로가기");
  function destination(label, section) {
    const button = node("button", "", label);
    button.type = "button";
    button.addEventListener("click", () => jumpTo(section));
    navigation.append(button);
    return section;
  }
  const copyActions = node("div", "copy-actions");
  copyActions.append(copyOutput({
    label: "요약 복사", fallbackLabel: "복사할 변경 요약",
    getText: () => [pull.title, pull.url, focusName, ...[...results.querySelectorAll(".result-section")].map(section => section.innerText)].join("\n\n"),
    successMessage: "변경 요약과 구조에 따른 검토 항목을 복사했습니다.",
  }), copyOutput({
    label: "분석 설정 링크 복사", fallbackLabel: "복사할 분석 설정 링크", rows: 3,
    getText: () => reviewURL(window.location.href, pull.url, options, focus),
    successMessage: "PR·관점·범위를 담은 링크를 복사했습니다. 이 링크에서 분석하면 최신 PR을 비교합니다.",
  }));
  results.append(navigation, copyActions);
  results.append(destination("코드 구조도", architectureSection(pull, report)));
  if (focus !== "db") {
    results.append(destination("API 변경", evidenceSection("라우트와 핸들러", report.routes, pull)));
    results.append(evidenceSection("SQLModel 데이터 모델과 지정한 응답 모델", report.responses, pull));
  }
  if (focus !== "api") {
    results.append(destination("DB 변경", evidenceSection("DB 컬럼과 마이그레이션 선언", report.migrations, pull)));
    results.append(evidenceSection("테이블 모델과 지정한 DB 모델", report.models, pull));
  }
  const reviewSection = node("section", "result-section");
  reviewSection.append(node("h3", "", "변경 파일과 추가 확인"));
  const reviewList = node("ul", "review-list");
  for (const [path, reasons] of report.review) {
    const item = node("li");
    const file = pull.files.find(value => value.path === path);
    const previous = file?.status === "removed";
    item.append(link(path, sourceURL(previous ? pull.baseRepo : pull.headRepo,
      previous ? pull.base : pull.head, previous ? file.previous_path : path)));
    if (reasons.length) item.append(node("p", "", reasons.join(" · ")));
    reviewList.append(item);
  }
  if (!report.review.length) reviewSection.append(node("p", "empty", "지정한 경로에 변경 파일이 없습니다."));
  else reviewSection.append(reviewList);
  results.append(destination("변경 파일", reviewSection));
  destination("입력 수정", document.querySelector("#pr-url"));
  results.append(node("p", "coverage-note", "라우터를 만드는 함수의 호출 여부, 최종 URL을 만드는 설정, 상속·다른 파일을 통한 영향, 실제 DB의 기존 데이터와 배포 순서는 별도 확인이 필요합니다."));
  results.hidden = false;
}

async function run(event) {
  event.preventDefault();
  if (busy || !form.reportValidity()) return;
  errorBox.hidden = true;
  errorBox.textContent = "";
  feedbackLink.href = feedbackURL();
  results.hidden = true;
  lastReport = null;
  busy = true;
  const controls = analysisControls();
  const controller = new AbortController();
  activeController = controller;
  cancelActions.hidden = false;
  let cancelled = false;
  const startedHash = window.location.hash;
  const timer = setTimeout(() => controller.abort(new DOMException("분석 제한시간 초과", "TimeoutError")), 90000);
  try {
    const pullURL = parsePullURL(document.querySelector("#pr-url").value).url;
    const options = { paths: lines("paths"), models: lines("models"), responses: lines("responses") };
    feedbackLink.href = feedbackURL({ url: pullURL }, null, options, form.elements.focus.value);
    controls.forEach(control => { control.disabled = true; });
    document.querySelector("#analyze-button").textContent = "분석 중…";
    const loading = loadPull(pullURL, controller.signal, progress, options.paths);
    jumpTo(status);
    const pull = await loading;
    const report = await analyze({ files: pull.files, ...options }, controller.signal, progress);
    controller.signal.throwIfAborted();
    lastReport = { pull, report, options };
    render(pull, report, options);
    progress("비교가 끝났습니다. 필요한 관점을 바꾸어 결과를 확인할 수 있습니다.");
    jumpTo(results);
  } catch (error) {
    cancelled = showAnalysisError(error, controller.signal);
  } finally {
    clearTimeout(timer);
    busy = false;
    activeController = null;
    cancelActions.hidden = true;
    controls.forEach(control => { control.disabled = false; });
    document.querySelector("#analyze-button").textContent = "변경 확인";
    if (window.location.hash !== startedHash) restoreSharedSettings();
    else if (cancelled) jumpTo(document.querySelector("#pr-url"));
  }
}

function restoreSharedSettings() {
  if (busy) return;
  try {
    const shared = reviewSettings(window.location.hash);
    if (!shared) return;
    selectMode("pr");
    document.querySelector("#pr-url").value = shared.url;
    form.elements.focus.value = shared.focus;
    for (const [id, values] of Object.entries(shared.options)) document.getElementById(id).value = values.join("\n");
    document.querySelector(".advanced-options").open = Object.values(shared.options).some(values => values.length);
    lastReport = null;
    results.hidden = true;
    errorBox.hidden = true;
    errorBox.textContent = "";
    feedbackLink.href = feedbackURL({ url: shared.url }, null, shared.options, shared.focus);
    progress("공유된 PR·관점·범위를 불러왔습니다. ‘변경 확인’을 누르면 최신 PR을 분석합니다.");
  } catch (error) {
    results.hidden = true;
    lastReport = null;
    errorBox.textContent = error.message;
    errorBox.hidden = false;
    progress("");
  }
}

async function runRepository(event) {
  event.preventDefault();
  if (busy || !repositoryForm.reportValidity()) return;
  results.hidden = true;
  lastReport = null;
  errorBox.hidden = true;
  feedbackLink.href = feedbackURL();
  busy = true;
  const controls = analysisControls();
  controls.forEach(control => { control.disabled = true; });
  const controller = new AbortController();
  activeController = controller;
  cancelActions.hidden = false;
  let cancelled = false;
  const timer = setTimeout(() => controller.abort(new DOMException("분석 제한시간 초과", "TimeoutError")), 90000);
  const startedHash = window.location.hash;
  document.getElementById("repository-analyze").textContent = "분석 중…";
  try {
    const loading = loadRepository(document.getElementById("repository-url").value,
      document.getElementById("repository-commit").value, document.getElementById("repository-root").value,
      controller.signal, progress);
    jumpTo(status);
    const snapshot = await loading;
    const report = await analyze({ kind: "repository", root: snapshot.root, files: snapshot.files, known_paths: snapshot.knownPaths }, controller.signal, progress);
    controller.signal.throwIfAborted();
    results.setAttribute("aria-label", "저장소 구조 분석 결과");
    results.replaceChildren(repositoryView(snapshot, report));
    results.hidden = false;
    progress("현재 구조를 확인했습니다. 파일과 사용 목적을 선택해 코드 근거와 검토 계획을 살펴보세요.");
    jumpTo(results);
  } catch (error) {
    cancelled = showAnalysisError(error, controller.signal);
  } finally {
    clearTimeout(timer);
    busy = false;
    activeController = null;
    cancelActions.hidden = true;
    controls.forEach(control => { control.disabled = false; });
    document.getElementById("repository-analyze").textContent = "현재 구조 확인";
    if (window.location.hash !== startedHash) restoreSharedSettings();
    else if (cancelled) jumpTo(document.querySelector("#repository-url"));
  }
}

restoreSharedSettings();
cancelButton.addEventListener("click", () => activeController?.abort());
for (const mode of ["pr", "repository"]) document.getElementById("mode-" + mode).addEventListener("click", () => selectMode(mode));
repositoryForm.addEventListener("submit", runRepository);
function repositoryExample(repo, commit, root) {
  document.getElementById("repository-url").value = "https://github.com/" + repo;
  document.getElementById("repository-commit").value = commit;
  document.getElementById("repository-root").value = root;
  repositoryForm.requestSubmit();
}
document.getElementById("repository-example").addEventListener("click", () =>
  repositoryExample("fastapi/full-stack-fastapi-template", "d0defd5a92bfcd35ccea93873519816a2252a97e", "backend"));
document.getElementById("repository-proposal-example").addEventListener("click", () =>
  repositoryExample("fastapi/sqlmodel", "c392a113ef555f626301f56e01a3a0312ef20ee8", "docs_src/tutorial/fastapi/simple_hero_api"));
window.addEventListener("hashchange", restoreSharedSettings);
form.addEventListener("submit", run);
document.querySelector("#example-button").addEventListener("click", () => {
  document.querySelector("#pr-url").value = exampleURL;
  form.requestSubmit();
});
for (const input of form.querySelectorAll('input[name="focus"]')) {
  input.addEventListener("change", () => {
    if (lastReport && !results.hidden) render(lastReport.pull, lastReport.report, lastReport.options);
  });
}
