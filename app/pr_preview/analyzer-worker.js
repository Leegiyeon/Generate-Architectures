import { loadPyodide } from "./pyodide/pyodide.mjs";

let runtime;

async function initialize() {
  const py = await loadPyodide({ indexURL: new URL("./pyodide/", self.location.href).href });
  py.FS.mkdirTree("/home/pyodide/scripts");
  py.FS.writeFile("/home/pyodide/scripts/__init__.py", "");
  const modules = ["preview_fastapi_pr.py", "preview_migration_evidence.py", "fastapi_routes.py",
    "python_module_scope.py", "sqlmodel_models.py", "pr_preview_browser.py", "pr_preview_structure.py", "repository_structure.py"];
  await Promise.all(modules.map(async name => {
    const response = await fetch("analyzer/" + name);
    if (!response.ok) throw new Error("분석 파일을 불러오지 못했습니다.");
    py.FS.writeFile("/home/pyodide/scripts/" + name, await response.text());
  }));
  py.runPython("from scripts.pr_preview_browser import analyze_json");
  py.runPython("from scripts.repository_structure import analyze_json as analyze_repository_json");
  return py;
}

self.onmessage = async event => {
  const { id, payload } = event.data;
  try {
    if (!runtime) runtime = initialize().catch(error => { runtime = null; throw error; });
    const py = await runtime;
    py.globals.set("_review_payload", JSON.stringify(payload));
    try {
      const expression = payload.kind === "repository" ? "analyze_repository_json(_review_payload)" : "analyze_json(_review_payload)";
      const result = JSON.parse(py.runPython(expression));
      self.postMessage({ id, result });
    } finally { py.globals.delete("_review_payload"); }
  } catch (error) {
    self.postMessage({ id, error: error.message });
  }
};
