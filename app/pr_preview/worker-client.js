let worker;
let requestId = 0;

/** The caller owns the deadline; cancelling also stops synchronous Python work. */
export async function analyze(payload, signal, progress = () => {}) {
  signal.throwIfAborted();
  if (!worker) worker = new Worker("./analyzer-worker.js", { type: "module" });
  const activeWorker = worker;
  const id = ++requestId;
  progress("브라우저 분석기를 준비하고 있습니다. 첫 실행은 잠시 걸립니다.");
  return new Promise((resolve, reject) => {
    let finished = false;
    function finish(succeeded, value) {
      if (finished) return;
      finished = true;
      activeWorker.removeEventListener("message", receive);
      activeWorker.removeEventListener("error", failed);
      signal.removeEventListener("abort", cancelled);
      if (succeeded) resolve(value);
      else {
        activeWorker.terminate();
        if (worker === activeWorker) worker = null;
        reject(value);
      }
    }
    function receive(event) {
      if (event.data?.id !== id) return;
      if (event.data.error) finish(false, new Error("소스 분석을 완료하지 못했습니다. " + event.data.error));
      else finish(true, event.data.result);
    }
    function failed() {
      finish(false, new Error("브라우저 분석기를 불러오지 못했습니다. 새로고침 후 다시 시도해 주세요."));
    }
    function cancelled() { finish(false, signal.reason); }
    activeWorker.addEventListener("message", receive);
    activeWorker.addEventListener("error", failed);
    signal.addEventListener("abort", cancelled, { once: true });
    if (signal.aborted) { cancelled(); return; }
    try { activeWorker.postMessage({ id, payload }); }
    catch (error) { finish(false, error); }
  });
}
