import { parsePullURL } from "./github.js";

const SCOPES = { paths: "path", models: "model", responses: "response" };
const MAX_HASH_LENGTH = 8000;
const INVALID_SETTINGS = "공유 링크의 분석 설정을 읽을 수 없습니다. PR 링크와 범위를 직접 입력해 주세요.";
const LONG_SETTINGS = "분석 설정이 너무 길어 링크로 공유할 수 없습니다. 경로와 모델 범위를 줄여 주세요.";

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
