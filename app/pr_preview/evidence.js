// Source expressions can themselves contain text resembling a source location.
export function evidenceLocation(entry, files) {
  if (entry.startsWith("  ")) return null;
  const matches = [...entry.matchAll(/(?:^| · )([^·]+\.py):(\d+)( \(이전 커밋\))?/g)];
  const match = matches.at(-1);
  if (!match) return null;
  const path = match[1].trim();
  const line = Number(match[2]);
  if (!files.some(file => file.path === path) || !Number.isSafeInteger(line) || line < 1 || line > 65536) return null;
  return { path, line, previous: Boolean(match[3]), start: match.index, length: match[0].length };
}
