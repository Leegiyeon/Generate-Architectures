import { parsePullURL } from "./github.js";
import { parseRepositoryURL, repositoryCommit, repositoryRoot, isRepositoryPath } from "./repository.js";

const SCOPES = { paths: "path", models: "model", responses: "response" };
const MAX_HASH_LENGTH = 8000;
const INVALID_SETTINGS = "공유 링크의 분석 설정을 읽을 수 없습니다. PR 링크와 범위를 직접 입력해 주세요.";
const LONG_SETTINGS = "분석 설정이 너무 길어 링크로 공유할 수 없습니다. 경로와 모델 범위를 줄여 주세요.";
const INVALID_REPOSITORY_SETTINGS = "공유 링크의 저장소 분석 설정을 읽을 수 없습니다. 저장소·커밋·소스 루트를 직접 입력해 주세요.";
const LONG_REPOSITORY_SETTINGS = "저장소 분석 설정이 너무 길어 링크로 공유할 수 없습니다. 소스 루트와 파일 경로 길이를 확인해 주세요.";

function checkedSettings(pullURL, options, focus) {
  if (!["all", "api", "db"].includes(focus)) throw new Error(INVALID_SETTINGS);
  const url = parsePullURL(pullURL).url;
  const selected = {};
  for (const key of Object.keys(SCOPES)) {
    const values = options[key] ?? [];
    if (!Array.isArray(values) || values.length > 30) throw new Error(LONG_SETTINGS);
    selected[key] = values.map(value => {
      if (typeof value !== "string" || !value.trim() || /[\u0000-\u001f\u007f\u2028\u2029]/.test(value)) {
        throw new Error(INVALID_SETTINGS);
      }
      if (value.length > 512) throw new Error(LONG_SETTINGS);
      return value.trim();
    });
  }
  return { url, focus, options: selected };
}

export function reviewURL(baseURL, pullURL, options = {}, focus = "all") {
  const settings = checkedSettings(pullURL, options, focus);
  const url = new URL(baseURL);
  if (!["https:", "http:"].includes(url.protocol) || url.username || url.password) throw new Error(INVALID_SETTINGS);
  const params = new URLSearchParams({ pr: settings.url, focus: settings.focus });
  for (const [key, parameter] of Object.entries(SCOPES)) {
    for (const value of settings.options[key]) params.append(parameter, value);
  }
  url.search = "";
  url.hash = params.toString();
  if (url.hash.length > MAX_HASH_LENGTH) throw new Error(LONG_SETTINGS);
  return url.href;
}

export function reviewSettings(hash) {
  if (!hash || hash === "#") return null;
  if (hash.length > MAX_HASH_LENGTH) throw new Error(LONG_SETTINGS);
  const params = new URLSearchParams(hash.replace(/^#/, ""));
  if (!params.has("pr")) return null;
  const allowed = new Set(["pr", "focus", ...Object.values(SCOPES)]);
  if (params.getAll("pr").length !== 1 || params.getAll("focus").length > 1
      || [...params.keys()].some(key => !allowed.has(key))) throw new Error(INVALID_SETTINGS);
  const options = Object.fromEntries(Object.entries(SCOPES).map(([key, parameter]) => [key, params.getAll(parameter)]));
  return checkedSettings(params.get("pr"), options, params.get("focus") ?? "all");
}

function checkedRepositorySettings(settings) {
  try {
    const { url: input, commit: inputCommit, root: inputRoot, file = "",
      direction = "outgoing", purpose = "onboarding" } = settings;
    if (inputRoot !== undefined && typeof inputRoot !== "string") throw new Error();
    const url = parseRepositoryURL(input).url;
    const commit = repositoryCommit(inputCommit);
    const root = repositoryRoot(inputRoot);
    if (!["outgoing", "incoming"].includes(direction)
        || !["onboarding", "change", "testing"].includes(purpose)
        || (file !== "" && (!isRepositoryPath(file) || !file.endsWith(".py")
          || (root !== "." && !file.startsWith(root + "/"))))) throw new Error();
    return { url, commit, root, file, direction, purpose };
  } catch { throw new Error(INVALID_REPOSITORY_SETTINGS); }
}

/** Share the analyzed commit, never the moving default branch. */
export function repositoryURL(baseURL, settings) {
  const selected = checkedRepositorySettings(settings);
  let url;
  try { url = new URL(baseURL); } catch { throw new Error(INVALID_REPOSITORY_SETTINGS); }
  if (!["https:", "http:"].includes(url.protocol) || url.username || url.password) {
    throw new Error(INVALID_REPOSITORY_SETTINGS);
  }
  const params = new URLSearchParams({ mode: "repository", repo: selected.url,
    commit: selected.commit, root: selected.root, direction: selected.direction, purpose: selected.purpose });
  if (selected.file) params.set("file", selected.file);
  url.search = "";
  url.hash = params.toString();
  if (url.hash.length > MAX_HASH_LENGTH) throw new Error(LONG_REPOSITORY_SETTINGS);
  return url.href;
}

export function repositorySettings(hash) {
  if (!hash || hash === "#") return null;
  if (hash.length > MAX_HASH_LENGTH) throw new Error(LONG_REPOSITORY_SETTINGS);
  const params = new URLSearchParams(hash.replace(/^#/, ""));
  if (!params.has("mode") && !params.has("repo")) return null;
  const allowed = new Set(["mode", "repo", "commit", "root", "file", "direction", "purpose"]);
  if (params.get("mode") !== "repository"
      || ["mode", "repo", "commit"].some(key => params.getAll(key).length !== 1)
      || [...params.keys()].some(key => !allowed.has(key) || params.getAll(key).length !== 1)) {
    throw new Error(INVALID_REPOSITORY_SETTINGS);
  }
  return checkedRepositorySettings({ url: params.get("repo"), commit: params.get("commit"),
    root: params.get("root") ?? undefined, file: params.get("file") ?? "",
    direction: params.get("direction") ?? "outgoing", purpose: params.get("purpose") ?? "onboarding" });
}
