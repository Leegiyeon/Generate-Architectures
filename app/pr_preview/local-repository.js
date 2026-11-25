import { isRepositoryPath, repositoryRoot } from "./repository.js";

const MAX_ENTRIES = 100000;
const MAX_PYTHON_FILES = 100;
const MAX_SOURCE_BYTES = 64 * 1024;
const UNSUPPORTED_PATH_CHARACTERS = /[\u0080-\u009f\u2028\u2029]/;
const EXCLUDED_DIRECTORIES = new Set([
  ".git", ".venv", ".env", "venv", "env", "node_modules", "__pycache__", "site-packages",
  ".tox", ".nox", ".cache", ".mypy_cache", ".pytest_cache", ".ruff_cache", "__pypackages__",
]);

// File reads cannot be interrupted by the File API. Stop waiting immediately,
// remove the listener, and ignore any eventual result when analysis is cancelled.
function readBytes(file, signal) {
  signal.throwIfAborted();
  return new Promise((resolve, reject) => {
    let finished = false;
    function finish(succeeded, value) {
      if (finished) return;
      finished = true;
      signal.removeEventListener("abort", cancelled);
      if (succeeded) resolve(value);
      else reject(value);
    }
    function cancelled() { finish(false, signal.reason); }
    signal.addEventListener("abort", cancelled, { once: true });
    if (signal.aborted) { cancelled(); return; }
    try {
      Promise.resolve(file.arrayBuffer()).then(
        value => finish(true, value), error => finish(false, error));
    } catch (error) { finish(false, error); }
  });
}

/** Read only browser-selected Python files; never fetch, execute or persist them. */
export async function loadLocalRepository(fileList, sourceRoot, signal, progress = () => {}) {
  const root = repositoryRoot(sourceRoot);
  if (UNSUPPORTED_PATH_CHARACTERS.test(root)) throw new Error("소스 루트는 제어문자가 없는 상대 경로여야 합니다.");
  signal.throwIfAborted();
  if (!fileList || typeof fileList[Symbol.iterator] !== "function") {
    throw new Error("분석할 프로젝트 폴더를 선택해 주세요.");
  }
  const candidates = [];
  const seen = new Set();
  let folder;
  let count = 0;
  let excluded = 0;
  let nonPython = 0;
  progress("선택한 폴더의 Python 파일 목록을 확인하고 있습니다.");
  for (const file of fileList) {
    signal.throwIfAborted();
    if (++count > MAX_ENTRIES) throw new Error("선택한 폴더의 파일이 100,000개를 초과합니다. 더 작은 프로젝트 폴더를 선택해 주세요.");
    const relative = file?.webkitRelativePath;
    if (!isRepositoryPath(relative) || UNSUPPORTED_PATH_CHARACTERS.test(relative)) {
      throw new Error("선택한 파일 목록에 올바르지 않은 상대 경로가 있습니다. 프로젝트 폴더를 다시 선택해 주세요.");
    }
    const parts = relative.split("/");
    if (parts.length < 2 || parts[0].includes(":")) {
      throw new Error("프로젝트 폴더 전체를 선택해 주세요. 폴더 기준 상대 경로가 필요합니다.");
    }
    if (folder !== undefined && folder !== parts[0]) throw new Error("여러 폴더의 파일이 섞여 있습니다. 프로젝트 폴더 하나를 다시 선택해 주세요.");
    folder = parts.shift();
    const path = parts.join("/");
    if (seen.has(path)) throw new Error("선택한 파일 목록에 중복 경로가 있습니다. 프로젝트 폴더를 다시 선택해 주세요.");
    seen.add(path);
    if (root !== "." && !path.startsWith(root + "/")) continue;
    if (!path.endsWith(".py")) { nonPython++; continue; }
    if (parts.slice(0, -1).some(part => EXCLUDED_DIRECTORIES.has(part.toLowerCase()))) {
      excluded++;
      continue;
    }
    candidates.push({ path, file });
  }
  signal.throwIfAborted();
  if (!count) throw new Error("선택한 폴더에 파일이 없습니다. 파일이 있는 프로젝트 폴더를 선택해 주세요.");
  candidates.sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0);
  const selected = candidates.slice(0, MAX_PYTHON_FILES);
  const warnings = ["선택한 파일의 현재 내용만 분석합니다. Git 커밋·변경 이력과 심볼릭 링크 여부는 확인하지 않습니다."];
  if (nonPython) warnings.push(`범위의 Python이 아닌 파일 ${nonPython}개는 읽지 않았습니다. .py 확장자만 지원합니다.`);
  if (excluded) warnings.push(`가상환경·의존성·캐시 폴더 안의 Python 파일 ${excluded}개를 제외했습니다.`);
  if (!candidates.length) warnings.push("지정한 소스 루트에서 분석 가능한 Python 파일을 찾지 못했습니다. 루트와 제외 폴더를 확인해 주세요.");
  if (candidates.length > selected.length) warnings.push(`선택한 루트의 Python 파일 ${candidates.length}개 중 ${selected.length}개만 읽습니다. 나머지 ${candidates.length - selected.length}개는 파일 수 제한으로 제외했습니다.`);
  const files = selected.map(({ path }) => ({ path, after: null, warnings: [] }));
  let next = 0;
  let completed = 0;
  const workers = Array.from({ length: Math.min(6, files.length) }, async () => {
    while (next < files.length) {
      signal.throwIfAborted();
      const index = next++;
      const file = files[index];
      const input = selected[index].file;
      if (!Number.isSafeInteger(input.size) || input.size < 0 || typeof input.arrayBuffer !== "function") {
        file.warnings.push("파일 정보를 확인할 수 없어 읽지 못함");
      } else if (input.size > MAX_SOURCE_BYTES) {
        file.warnings.push("파일이 64 KiB를 초과해 읽지 못함");
      } else {
        try {
          const buffer = await readBytes(input, signal);
          signal.throwIfAborted();
          if (!(buffer instanceof ArrayBuffer)) throw new Error("Invalid file contents");
          if (buffer.byteLength > MAX_SOURCE_BYTES) file.warnings.push("파일이 64 KiB를 초과해 읽지 못함");
          else {
            try { file.after = new TextDecoder("utf-8", { fatal: true }).decode(buffer); }
            catch { file.warnings.push("UTF-8 텍스트가 아니어서 읽지 못함"); }
          }
        } catch (error) {
          if (signal.aborted) throw signal.reason;
          file.warnings.push("파일을 읽지 못했습니다. 접근 권한을 확인하고 폴더를 다시 선택해 주세요.");
        }
      }
      signal.throwIfAborted();
      progress(`선택한 폴더의 Python 소스를 읽고 있습니다. ${++completed} / ${files.length}`);
    }
  });
  await Promise.all(workers);
  signal.throwIfAborted();
  const unreadable = files.filter(file => file.after === null).length;
  if (unreadable) warnings.push(`선택한 Python 파일 ${files.length}개 중 ${unreadable}개의 소스를 읽지 못했습니다. 해당 파일은 미확인으로 남깁니다.`);
  return { source: "local", kind: "repository", repo: folder, head: "", root, files,
    knownPaths: candidates.map(({ path }) => path), totalFiles: candidates.length,
    fetchedAt: new Date().toISOString(), warnings };
}
