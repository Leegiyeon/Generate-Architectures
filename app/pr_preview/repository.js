import { githubJSON, sourceText } from "./github.js";

const MAX_PYTHON_FILES = 100;
const MAX_SOURCE_BYTES = 64 * 1024;
const cache = new Map();
const missingMessage = "공개 저장소 또는 지정한 커밋을 찾을 수 없습니다. 주소와 커밋을 확인해 주세요.";

export function parseRepositoryURL(input) {
  let url;
  try { url = new URL(input.trim()); } catch { throw new Error("GitHub 저장소 링크를 입력해 주세요."); }
  const match = url.pathname.match(/^\/([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+)\/?$/);
  if (url.protocol !== "https:" || url.host !== "github.com" || url.username || url.password || !match) {
    throw new Error("https://github.com/소유자/저장소 형식의 공개 저장소 링크가 필요합니다.");
  }
  const repo = match[1] + "/" + match[2].replace(/\.git$/, "");
  if (!repo.split("/").every(part => part && part !== "." && part !== "..")) {
    throw new Error("올바른 GitHub 저장소 이름을 입력해 주세요.");
  }
  return { repo, url: "https://github.com/" + repo };
}

export function repositoryCommit(input) {
  const value = typeof input === "string" ? input.trim().toLowerCase() : "";
  if (!/^[a-f0-9]{40}$/.test(value)) throw new Error("고정할 커밋의 전체 SHA 40자리를 입력해 주세요.");
  return value;
}

export function isRepositoryPath(path) {
  return typeof path === "string" && path.length > 0 && path.length <= 1000
    && !/[\\\u0000-\u001f\u007f]/.test(path)
    && path.split("/").every(part => part && part !== "." && part !== "..");
}

export function repositoryRoot(input) {
  const value = typeof input === "string" ? input.trim() : "";
  if (!value || value === ".") return ".";
  const root = value.replace(/\/$/, "");
  if (!isRepositoryPath(root) || root.split("/")[0].includes(":")) {
    throw new Error("소스 루트는 . 또는 backend 같은 저장소 상대 경로로 입력해 주세요.");
  }
  return root;
}

export async function loadRepository(input, commit, sourceRoot, signal, progress = () => {}) {
  const parsed = parseRepositoryURL(input);
  const latest = commit === undefined || (typeof commit === "string" && !commit.trim());
  let head = latest ? null : repositoryCommit(commit);
  const root = repositoryRoot(sourceRoot);
  signal.throwIfAborted();
  let key = head ? JSON.stringify([parsed.repo.toLowerCase(), head, root]) : null;
  let existing = head ? cache.get(key) : null;
  if (existing && Date.now() - existing.time < 180000) {
    progress("방금 조회한 고정 커밋의 저장소 소스를 분석하고 있습니다.");
    return existing.value;
  }
  progress("공개 저장소와 고정 커밋의 파일 목록을 확인하고 있습니다.");
  const metadata = await githubJSON("/repos/" + parsed.repo, signal, missingMessage);
  if (metadata.private !== false) throw new Error("공개 저장소만 분석할 수 있습니다.");
  if (typeof metadata.full_name !== "string" || metadata.full_name.toLowerCase() !== parsed.repo.toLowerCase()) {
    throw new Error("저장소 정보를 확인할 수 없습니다.");
  }
  const repo = parsed.repo;
  const endpoint = "/repos/" + repo;
  let treeSHA;
  let resolvedFrom;
  if (latest) {
    const branch = metadata.default_branch;
    if (typeof branch !== "string" || !branch || branch.length > 1000 || /[\u0000-\u0020\u007f]/.test(branch)) {
      throw new Error("저장소의 기본 브랜치를 확인할 수 없습니다. 전체 커밋 SHA를 지정해 주세요.");
    }
    progress("기본 브랜치의 최신 커밋을 고정하고 있습니다.");
    // Explicit heads/ avoids resolving a same-named tag; all subsequent reads use the SHA.
    const pinned = await githubJSON(endpoint + "/commits/" + encodeURIComponent("heads/" + branch) + "?per_page=1", signal, missingMessage);
    signal.throwIfAborted();
    if (typeof pinned?.sha !== "string" || !/^[a-f0-9]{40}$/.test(pinned.sha)
        || typeof pinned.commit?.tree?.sha !== "string" || !/^[a-f0-9]{40}$/.test(pinned.commit.tree.sha)) {
      throw new Error("기본 브랜치의 커밋과 파일 목록을 확인할 수 없습니다.");
    }
    head = pinned.sha;
    treeSHA = pinned.commit.tree.sha;
    resolvedFrom = { branch };
    key = JSON.stringify([parsed.repo.toLowerCase(), head, root]);
    existing = cache.get(key);
    if (existing && Date.now() - existing.time < 180000) {
      progress("확인한 최신 커밋의 저장소 소스를 다시 분석하고 있습니다.");
      return { ...existing.value, resolvedFrom };
    }
  } else {
    const pinned = await githubJSON(endpoint + "/git/commits/" + head, signal, missingMessage);
    if (pinned.sha !== head || !/^[a-f0-9]{40}$/.test(pinned.tree?.sha)) {
      throw new Error("지정한 커밋의 파일 목록을 확인할 수 없습니다.");
    }
    treeSHA = pinned.tree.sha;
  }
  const listing = await githubJSON(endpoint + "/git/trees/" + treeSHA + "?recursive=1", signal, missingMessage);
  if (listing.truncated !== false) throw new Error("저장소 파일 목록이 잘렸습니다. 전체 범위를 확인할 수 없어 분석하지 않았습니다.");
  if (listing.sha !== treeSHA || !Array.isArray(listing.tree) || listing.tree.length > 100000) {
    throw new Error("저장소 파일 목록을 확인할 수 없습니다.");
  }
  const warnings = [];
  const candidates = [];
  const knownPaths = [];
  const seen = new Set();
  let excludedLinks = 0;
  for (const entry of listing.tree) {
    if (!isRepositoryPath(entry.path)) throw new Error("저장소 파일 목록에 올바르지 않은 경로가 있습니다.");
    if (root !== "." && !entry.path.startsWith(root + "/")) continue;
    if (!entry.path.endsWith(".py")) continue;
    if (seen.has(entry.path)) throw new Error("저장소 파일 목록에 중복 경로가 있습니다.");
    seen.add(entry.path);
    if (entry.type === "blob") knownPaths.push(entry.path);
    if (entry.type !== "blob" || !["100644", "100755"].includes(entry.mode)) {
      excludedLinks++;
      continue;
    }
    candidates.push(entry);
  }
  knownPaths.sort();
  candidates.sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0);
  const selected = candidates.slice(0, MAX_PYTHON_FILES);
  if (!candidates.length) warnings.push("지정한 소스 루트에서 분석 가능한 일반 Python 파일을 찾지 못했습니다.");
  if (candidates.length > selected.length) warnings.push(`선택한 루트의 Python 파일 ${candidates.length}개 중 ${selected.length}개만 읽습니다. 나머지 ${candidates.length - selected.length}개는 파일 수 제한으로 제외했습니다.`);
  if (excludedLinks) warnings.push(`심볼릭 링크·일반 파일이 아닌 Python 경로 ${excludedLinks}개를 제외했습니다.`);
  const files = selected.map(entry => ({ path: entry.path, after: null, warnings: [] }));
  let next = 0;
  let completed = 0;
  const workers = Array.from({ length: Math.min(6, files.length) }, async () => {
    while (next < files.length) {
      signal.throwIfAborted();
      const index = next++;
      const file = files[index];
      const size = selected[index].size;
      if (Number.isSafeInteger(size) && size > MAX_SOURCE_BYTES) {
        file.warnings.push("파일이 64 KiB를 초과해 읽지 못함");
      } else {
        try { file.after = await sourceText(repo, head, file.path, signal); }
        catch (error) {
          if (signal.aborted || error.name === "AbortError") throw error;
          file.warnings.push(error.message);
        }
      }
      signal.throwIfAborted();
      progress(`고정 커밋의 Python 소스를 읽고 있습니다. ${++completed} / ${files.length}`);
    }
  });
  await Promise.all(workers);
  signal.throwIfAborted();
  const unreadable = files.filter(file => file.after === null).length;
  if (unreadable) warnings.push(`선택한 Python 파일 ${files.length}개 중 ${unreadable}개의 소스를 읽지 못했습니다. 해당 파일은 미확인으로 남깁니다.`);
  const value = { ...parsed, kind: "repository", head, headRepo: repo, root, files, knownPaths,
    totalFiles: candidates.length, fetchedAt: new Date().toISOString(), warnings };
  if (!unreadable) {
    if (cache.size >= 2) cache.delete(cache.keys().next().value);
    cache.set(key, { time: Date.now(), value });
  }
  return resolvedFrom ? { ...value, resolvedFrom } : value;
}
