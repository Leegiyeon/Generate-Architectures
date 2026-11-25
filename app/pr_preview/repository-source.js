import { sourceURL } from "./github.js";

export const isLocalRepository = snapshot => snapshot.source === "local";
export const selectionTime = snapshot => snapshot.fetchedAt || "미확인";
const oneLine = value => String(value).replace(/[\r\n]+/g, " ");

export function repositoryIdentityText(snapshot) {
  return isLocalRepository(snapshot)
    ? [`로컬 폴더: ${oneLine(snapshot.repo)}`, `선택 시각: ${oneLine(selectionTime(snapshot))}`,
      "선택 시점의 현재 구조입니다. 이전 상태와의 변경 비교는 포함하지 않습니다."]
    : [`저장소: ${oneLine(snapshot.repo)}`, `커밋: ${oneLine(snapshot.head)}`];
}

export function localCodeContext(snapshot, path, line) {
  const file = snapshot.files?.find(item => item.path === path);
  if (typeof file?.after !== "string" || !Number.isSafeInteger(line) || line < 1) return null;
  const lines = file.after.split(/\r\n?|\n/);
  if (line > lines.length) return null;
  const start = Math.max(1, line - 3);
  const end = Math.min(lines.length, line + 3);
  return { start, end, text: lines.slice(start - 1, end)
    .map((text, index) => `${start + index === line ? ">" : " "} ${start + index} | ${text}`).join("\n") };
}

export function repositoryEvidenceText(snapshot, path, line) {
  if (!isLocalRepository(snapshot)) return sourceURL(snapshot.repo, snapshot.head, path, line);
  return `${localCodeContext(snapshot, path, line) ? "로컬 코드" : "로컬 코드 근거 미확인"}: ${oneLine(path)}:${oneLine(line)} · 선택 시각: ${oneLine(selectionTime(snapshot))}`;
}
