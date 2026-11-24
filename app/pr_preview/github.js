const API = "https://api.github.com";
const MAX_CHANGED_FILES = 300;
const MAX_PYTHON_FILES = 100;
const MAX_SOURCE_BYTES = 64 * 1024;
const cache = new Map();

export function parsePullURL(input) {
  let url;
  try { url = new URL(input.trim()); } catch { throw new Error("GitHub PR 링크를 입력해 주세요."); }
  const match = url.pathname.match(/^\/([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+)\/pull\/([1-9][0-9]*)(?:\/(?:files|commits|checks))?\/?$/);
  if (url.protocol !== "https:" || url.host !== "github.com" || url.username || url.password || !match) {
    throw new Error("https://github.com/소유자/저장소/pull/번호 형식의 공개 PR 링크가 필요합니다.");
  }
  return { repo: match[1] + "/" + match[2], number: match[3],
    url: "https://github.com/" + match[1] + "/" + match[2] + "/pull/" + match[3] };
}

export async function githubJSON(path, signal, missingMessage = "공개 PR을 찾을 수 없습니다. 저장소와 PR 번호를 확인해 주세요.") {
  const response = await fetch(API + path, {
    headers: { Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" },
    signal, credentials: "omit", redirect: "error",
  });
  if (response.status === 403 || response.status === 429) {
    const reset = Number(response.headers.get("x-ratelimit-reset"));
    const when = reset ? " " + new Date(reset * 1000).toLocaleTimeString("ko-KR") + " 이후 다시 시도해 주세요." : " 잠시 후 다시 시도해 주세요.";
    throw new Error("GitHub 조회 한도에 도달했거나 접근이 제한되었습니다." + when);
  }
  if (response.status === 404) throw new Error(missingMessage);
  if (!response.ok) throw new Error("GitHub 조회에 실패했습니다. HTTP " + response.status);
  return response.json();
}

function checkedRepository(name) {
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(name)) throw new Error("저장소 정보를 확인할 수 없습니다.");
  return name;
}

function checkedSHA(value) {
  if (!/^[a-f0-9]{40}$/.test(value)) throw new Error("PR 커밋 정보를 확인할 수 없습니다.");
  return value;
}

export function sourceURL(repo, sha, path, line) {
  const encodedPath = path.split("/").map(encodeURIComponent).join("/");
  return "https://github.com/" + repo + "/blob/" + sha + "/" + encodedPath + (line ? "#L" + line : "");
}

export async function sourceText(repo, sha, path, signal) {
  const encodedPath = path.split("/").map(encodeURIComponent).join("/");
  const url = "https://raw.githubusercontent.com/" + repo + "/" + sha + "/" + encodedPath;
  const response = await fetch(url, { signal, credentials: "omit", redirect: "error" });
  if (!response.ok) throw new Error("소스를 읽지 못함 (HTTP " + response.status + ")");
  const reader = response.body.getReader();
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_SOURCE_BYTES) {
        await reader.cancel();
        throw new Error("파일이 64 KiB를 초과함");
      }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  try { return new TextDecoder("utf-8", { fatal: true }).decode(bytes); }
  catch { throw new Error("UTF-8 소스로 읽지 못함"); }
}

export async function loadPull(input, signal, progress) {
  const pull = parsePullURL(input);
  const existing = cache.get(pull.url);
  if (existing && Date.now() - existing.time < 180000) {
    progress("방금 조회한 PR 소스로 비교하고 있습니다.");
    return existing.value;
  }
  progress("공개 PR과 비교 기준 커밋을 확인하고 있습니다.");
  const endpoint = "/repos/" + pull.repo + "/pulls/" + pull.number;
  const metadata = await githubJSON(endpoint, signal);
  if (metadata.base.repo.private || metadata.head.repo?.private) throw new Error("공개 저장소의 PR을 입력해 주세요.");
  const baseRepo = checkedRepository(metadata.base.repo.full_name);
  const headRepo = checkedRepository(metadata.head.repo?.full_name || baseRepo);
  const baseTip = checkedSHA(metadata.base.sha);
  const head = checkedSHA(metadata.head.sha);
  const comparison = await githubJSON("/repos/" + baseRepo + "/compare/" + baseTip + "..." + head + "?per_page=1", signal);
  const base = checkedSHA(comparison.merge_base_commit.sha);
  const changed = [];
  for (let page = 1; changed.length < Math.min(metadata.changed_files, MAX_CHANGED_FILES); page++) {
    const batch = await githubJSON(endpoint + "/files?per_page=100&page=" + page, signal);
    changed.push(...batch.slice(0, MAX_CHANGED_FILES - changed.length));
    if (batch.length < 100) break;
  }
  const files = changed.map(file => ({
    path: file.filename, previous_path: file.previous_filename || file.filename,
    status: file.status, before: null, after: null, warnings: [],
  }));
  const pythonFiles = files.filter(file => file.path.endsWith(".py"));
  const selected = pythonFiles.slice(0, MAX_PYTHON_FILES);
  for (const file of pythonFiles.slice(MAX_PYTHON_FILES)) file.warnings.push("Python 파일 100개를 초과해 소스를 읽지 못함");
  const tasks = selected.flatMap(file => ["before", "after"].map(side => ({ file, side })));
  let next = 0;
  let completed = 0;
  const workers = Array.from({ length: Math.min(6, tasks.length) }, async () => {
    while (next < tasks.length) {
      const { file, side } = tasks[next++];
      const missing = (side === "before" && file.status === "added") || (side === "after" && file.status === "removed");
      if (missing) file[side] = "";
      else {
        try {
          file[side] = await sourceText(side === "before" ? baseRepo : headRepo,
            side === "before" ? base : head, side === "before" ? file.previous_path : file.path, signal);
        } catch (error) {
          if (signal.aborted) throw error;
          file.warnings.push((side === "before" ? "이전" : "이후") + " · " + error.message);
        }
      }
      completed++;
      progress("변경 소스를 읽고 있습니다. " + completed + " / " + tasks.length);
    }
  });
  await Promise.all(workers);
  const current = await githubJSON(endpoint, signal);
  if (current.head.sha !== head || current.base.sha !== baseTip) {
    throw new Error("조회 중 PR 커밋이 바뀌었습니다. 다시 분석해 주세요.");
  }
  const value = { ...pull, title: metadata.title, base, head, baseRepo, headRepo,
    files, totalFiles: metadata.changed_files, fetchedAt: new Date().toISOString(),
    warnings: metadata.changed_files > changed.length ? ["변경 파일 " + metadata.changed_files + "개 중 " + changed.length + "개를 읽었습니다."] : [] };
  if (cache.size >= 4) cache.delete(cache.keys().next().value);
  cache.set(pull.url, { time: Date.now(), value });
  return value;
}
