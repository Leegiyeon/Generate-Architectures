import { loadPull, parsePullURL, sourceURL } from "./github.js";
import { feedbackURL } from "./feedback.js";
import { reviewSettings, reviewURL } from "./review-link.js";
import { architectureSection } from "./architecture.js";
import { evidenceLocation } from "./evidence.js";
import { loadRepository } from "./repository.js";
import { repositoryView } from "./repository-view.js";

const form = document.querySelector("#review-form");
const repositoryForm = document.querySelector("#repository-form");
const results = document.querySelector("#results");
const status = document.querySelector("#status");
const errorBox = document.querySelector("#error");
const feedbackLink = document.querySelector("#feedback-link");
feedbackLink.href = feedbackURL();
const exampleURL = "https://github.com/fastapi/full-stack-fastapi-template/pull/2144";
let worker;
let requestId = 0;
let lastReport;
let busy = false;

function selectMode(mode) {
  if (busy) return;
  document.querySelector(".intro h1").textContent = mode === "repository" ? "현재 코드는 어떻게 연결되나요?" : "API와 DB에서 무엇이 바뀌었나요?";
  document.querySelector(".intro p").textContent = mode === "repository" ? "저장소와 커밋을 지정하고, 파일별 import와 라우트·모델 선언을 확인하세요." : "PR 링크를 넣고, 관련 코드 구조와 변경 사항을 코드 근거와 함께 확인하세요.";
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

function analyze(payload) {
  if (!worker) worker = new Worker("./analyzer-worker.js", { type: "module" });
  const activeWorker = worker;
  const id = ++requestId;
  progress("브라우저 분석기를 준비하고 있습니다. 첫 실행은 잠시 걸립니다.");
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => finish(new Error("분석 준비 시간이 초과되었습니다. 네트워크를 확인하고 다시 시도해 주세요.")), 90000);
    function finish(error, result) {
      clearTimeout(timer);
      activeWorker.removeEventListener("message", receive);
      activeWorker.removeEventListener("error", failed);
      if (error) {
        activeWorker.terminate();
        if (worker === activeWorker) worker = null;
        reject(error);
      } else resolve(result);
    }
    function receive(event) {
      if (event.data.id !== id) return;
      if (event.data.error) finish(new Error("소스 분석을 완료하지 못했습니다. " + event.data.error));
      else finish(null, event.data.result);
    }
    function failed() { finish(new Error("브라우저 분석기를 불러오지 못했습니다. 새로고침 후 다시 시도해 주세요.")); }
    activeWorker.addEventListener("message", receive);
    activeWorker.addEventListener("error", failed);
    activeWorker.postMessage({ id, payload });
  });
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
  results.append(architectureSection(pull, report));
  if (focus !== "db") {
    results.append(evidenceSection("라우트와 핸들러", report.routes, pull));
    results.append(evidenceSection("SQLModel 데이터 모델과 지정한 응답 모델", report.responses, pull));
  }
  if (focus !== "api") {
    results.append(evidenceSection("DB 컬럼과 마이그레이션 선언", report.migrations, pull));
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
  results.append(reviewSection);
  results.append(node("p", "coverage-note", "라우터를 만드는 함수의 호출 여부, 최종 URL을 만드는 설정, 상속·다른 파일을 통한 영향, 실제 DB의 기존 데이터와 배포 순서는 별도 확인이 필요합니다."));
  const actions = node("div", "report-actions");
  const copy = node("button", "", "요약 복사");
  copy.type = "button";
  copy.addEventListener("click", async () => {
    const text = [pull.title, pull.url, focusName, ...[...results.querySelectorAll(".result-section")].map(section => section.innerText)].join("\n\n");
    try {
      await navigator.clipboard.writeText(text);
      progress("변경 요약과 구조에 따른 검토 항목을 복사했습니다.");
    } catch { progress("브라우저가 복사를 허용하지 않았습니다. 결과 텍스트를 선택해 복사해 주세요."); }
  });
  const share = node("button", "", "분석 설정 링크 복사");
  share.type = "button";
  share.addEventListener("click", async () => {
    let url;
    try { url = reviewURL(window.location.href, pull.url, options, focus); }
    catch (error) { progress(error.message); return; }
    try {
      await navigator.clipboard.writeText(url);
      progress("PR·관점·범위가 담긴 링크를 복사했습니다. 링크를 받은 사람이 분석을 실행하면 최신 PR을 비교합니다.");
    } catch { progress("브라우저가 링크 복사를 허용하지 않았습니다. 복사 권한을 확인하고 다시 시도해 주세요."); }
  });
  actions.append(copy, share);
  results.append(actions);
  results.hidden = false;
}

async function run(event) {
  event.preventDefault();
  if (busy || !form.reportValidity()) return;
  errorBox.hidden = true;
  errorBox.textContent = "";
  feedbackLink.href = feedbackURL();
  results.hidden = true;
  busy = true;
  const controls = analysisControls();
  const controller = new AbortController();
  const startedHash = window.location.hash;
  const timer = setTimeout(() => controller.abort(), 90000);
  try {
    const pullURL = parsePullURL(document.querySelector("#pr-url").value).url;
    const options = { paths: lines("paths"), models: lines("models"), responses: lines("responses") };
    feedbackLink.href = feedbackURL({ url: pullURL }, null, options, form.elements.focus.value);
    controls.forEach(control => { control.disabled = true; });
    document.querySelector("#analyze-button").textContent = "분석 중…";
    const pull = await loadPull(pullURL, controller.signal, progress);
    const report = await analyze({ files: pull.files, ...options });
    lastReport = { pull, report, options };
    render(pull, report, options);
    progress("비교가 끝났습니다. 필요한 관점을 바꾸어 결과를 확인할 수 있습니다.");
  } catch (error) {
    errorBox.textContent = error.name === "AbortError" ? "GitHub 응답 시간이 초과되었습니다. 다시 시도해 주세요." : error.message;
    errorBox.hidden = false;
    progress("");
  } finally {
    clearTimeout(timer);
    busy = false;
    controls.forEach(control => { control.disabled = false; });
    document.querySelector("#analyze-button").textContent = "변경 요약 보기";
    if (window.location.hash !== startedHash) restoreSharedSettings();
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
  const timer = setTimeout(() => controller.abort(), 90000);
  const startedHash = window.location.hash;
  document.getElementById("repository-analyze").textContent = "분석 중…";
  try {
    const snapshot = await loadRepository(document.getElementById("repository-url").value,
      document.getElementById("repository-commit").value, document.getElementById("repository-root").value,
      controller.signal, progress);
    const report = await analyze({ kind: "repository", root: snapshot.root, files: snapshot.files, known_paths: snapshot.knownPaths });
    results.setAttribute("aria-label", "저장소 구조 분석 결과");
    results.replaceChildren(repositoryView(snapshot, report));
    results.hidden = false;
    progress("현재 구조를 확인했습니다. 파일과 사용 목적을 선택해 코드 근거와 검토 계획을 살펴보세요.");
  } catch (error) {
    errorBox.textContent = error.name === "AbortError" ? "저장소 조회 시간이 초과되었습니다. 범위를 줄여 다시 시도해 주세요." : error.message;
    errorBox.hidden = false;
    progress("");
  } finally {
    clearTimeout(timer);
    busy = false;
    controls.forEach(control => { control.disabled = false; });
    document.getElementById("repository-analyze").textContent = "현재 구조 확인";
    if (window.location.hash !== startedHash) restoreSharedSettings();
  }
}

restoreSharedSettings();
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
