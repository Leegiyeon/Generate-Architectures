// Classic script: this recovery path must work even when ES modules cannot load.
(() => {
  const notice = document.getElementById("startup-notice");
  const title = document.getElementById("startup-title");
  const message = document.getElementById("startup-message");
  const service = document.getElementById("startup-service");
  let ready = false;

  // Keep native GET submission from replacing the page before handlers exist.
  for (const form of document.querySelectorAll("#review-form, #repository-form")) {
    form.addEventListener("submit", event => { if (!ready) event.preventDefault(); }, true);
  }

  function recoveryURL() {
    const destination = new URL(document.querySelector('link[rel="canonical"]').href);
    const shared = new URLSearchParams(location.hash.slice(1));
    const legacy = new URLSearchParams(location.search);
    const params = new URLSearchParams();
    const keys = shared.has("pr") ? ["pr", "focus", "path", "model", "response"]
      : shared.has("repo") ? ["mode", "repo", "commit", "root", "file", "direction", "purpose"] : [];
    for (const key of keys) for (const value of shared.getAll(key)) params.append(key, value);
    if (!keys.length && legacy.has("pr-url")) {
      params.set("pr", legacy.get("pr-url"));
      params.set("focus", legacy.get("focus") || "all");
      for (const [field, key] of [["paths", "path"], ["models", "model"], ["responses", "response"]]) {
        for (const value of (legacy.get(field) || "").split(/\r?\n/).map(value => value.trim()).filter(Boolean)) {
          params.append(key, value);
        }
      }
    }
    // Never carry embedded credentials, URL query tokens or a local file path.
    // The destination's shared-settings parser validates scope before analysis.
    for (const [key, value] of params) {
      const selected = value.trim();
      if (!["pr", "repo"].includes(key)
          && (/^[\\/]|^~[\\/]|^[A-Za-z]:[\\/]|[A-Za-z][A-Za-z0-9+.-]*:\/\//.test(selected)
            || /^(?:file|data|javascript|mailto):/i.test(selected))) return destination.href;
    }
    const targetKey = params.has("pr") ? "pr" : "repo";
    if (params.has(targetKey)) {
      const target = new URL(params.get(targetKey));
      if (target.protocol !== "https:" || target.host !== "github.com" || target.username || target.password) {
        return destination.href;
      }
      params.set(targetKey, target.origin + target.pathname);
    }
    destination.hash = params.toString();
    return destination.hash.length <= 8000 ? destination.href : destination.origin + destination.pathname;
  }
  try { service.href = recoveryURL(); } catch { /* The static service link remains usable. */ }
  if (new URL(service.href).hash) service.textContent = "입력한 설정으로 웹서비스 열기";

  function failed(heading, detail) {
    title.textContent = heading;
    message.textContent = detail;
    notice.hidden = false;
  }
  if (location.protocol === "file:") {
    failed("HTML 파일을 직접 열어 분석할 수 없습니다",
      "아래 링크로 웹서비스를 열어 주세요. 로컬 실행은 ZIP 전체를 풀고 아래 실행 방법을 따라 주세요.");
    return;
  }

  function initializationError() {
    if (!ready) failed("분석 화면을 시작하지 못했습니다",
      "분석 파일을 읽거나 초기화하지 못했습니다. 새로고침하거나 아래 웹서비스에서 다시 열어 주세요.");
  }
  window.addEventListener("error", initializationError);
  document.addEventListener("review-ready", () => {
    ready = true;
    for (const control of document.querySelectorAll("[data-startup-lock]")) control.disabled = false;
    notice.hidden = true;
    window.removeEventListener("error", initializationError);
  }, { once: true });
  const application = document.createElement("script");
  application.type = "module";
  application.src = "app.js";
  application.addEventListener("error", initializationError);
  document.head.append(application);
})();
