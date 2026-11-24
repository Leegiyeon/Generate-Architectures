/** Keep copy feedback and a selectable fallback beside the action that created it. */
export function copyOutput({ label, getText, successMessage, fallbackLabel, rows = 8 }) {
  const container = document.createElement("div");
  container.className = "copy-output";
  const actions = document.createElement("div");
  actions.className = "report-actions";
  const copy = document.createElement("button");
  copy.type = "button";
  copy.textContent = label;
  actions.append(copy);
  const status = document.createElement("p");
  status.className = "status";
  status.setAttribute("role", "status");
  const manual = document.createElement("details");
  manual.className = "copy-output-manual";
  const summary = document.createElement("summary");
  summary.textContent = fallbackLabel + " 보기";
  const field = document.createElement("label");
  field.className = "advanced-field";
  field.textContent = fallbackLabel;
  const text = document.createElement("textarea");
  text.readOnly = true;
  text.rows = rows;
  field.append(text);
  manual.append(summary, field);
  container.append(actions, status, manual);

  function value() {
    const result = getText();
    if (typeof result !== "string" || !result.length) throw new Error("복사할 내용을 준비하지 못했습니다.");
    return result;
  }

  function preparationFailed(error) {
    text.value = "";
    manual.open = false;
    status.textContent = error?.message || "복사할 내용을 준비하지 못했습니다.";
  }

  function selectText() {
    text.focus();
    text.select();
  }

  manual.addEventListener("toggle", () => {
    if (!container.isConnected) return;
    if (!manual.open) { text.value = ""; return; }
    try {
      if (!text.value) text.value = value();
      selectText();
    } catch (error) { preparationFailed(error); }
  });

  copy.addEventListener("click", async () => {
    if (copy.disabled) return;
    copy.disabled = true;
    status.textContent = "";
    manual.open = false;
    text.value = "";
    let payload;
    try { payload = value(); }
    catch (error) {
      preparationFailed(error);
      copy.disabled = false;
      return;
    }
    try {
      await navigator.clipboard.writeText(payload);
      if (container.isConnected) status.textContent = successMessage;
    } catch {
      if (container.isConnected) {
        text.value = payload;
        manual.open = true;
        selectText();
        status.textContent = "자동 복사가 허용되지 않아 텍스트를 펼쳤습니다. 선택한 내용을 복사하세요(Mac: ⌘C, Windows·Linux: Ctrl+C).";
      }
    } finally { copy.disabled = false; }
  });
  return container;
}
