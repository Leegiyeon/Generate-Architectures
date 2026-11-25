import assert from "node:assert/strict";
import test from "node:test";

let moduleId = 0;
async function client(t) {
  const instances = [];
  class Worker {
    constructor(url, options) {
      this.url = url;
      this.options = options;
      this.listeners = new Map();
      this.messages = [];
      this.terminated = 0;
      instances.push(this);
    }
    addEventListener(type, listener) {
      if (!this.listeners.has(type)) this.listeners.set(type, new Set());
      this.listeners.get(type).add(listener);
    }
    removeEventListener(type, listener) { this.listeners.get(type)?.delete(listener); }
    postMessage(message) {
      if (Worker.postError) throw Worker.postError;
      this.messages.push(message);
    }
    emit(type, event) {
      for (const listener of [...(this.listeners.get(type) || [])]) listener(event);
    }
    reply(result, id = this.messages.at(-1).id) { this.emit("message", { data: { id, result } }); }
    terminate() { this.terminated++; }
  }
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "Worker");
  Object.defineProperty(globalThis, "Worker", { value: Worker, configurable: true });
  t.after(() => {
    if (descriptor) Object.defineProperty(globalThis, "Worker", descriptor);
    else delete globalThis.Worker;
  });
  const url = new URL("../app/pr_preview/worker-client.js", import.meta.url);
  url.searchParams.set("test", String(++moduleId));
  const { analyze } = await import(url.href);
  return { analyze, instances, Worker };
}

function noListeners(worker) {
  assert.equal(worker.listeners.get("message").size, 0);
  assert.equal(worker.listeners.get("error").size, 0);
}

test("success preserves the warm Worker, separates request IDs and removes completed listeners", async t => {
  const { analyze, instances } = await client(t);
  const progress = [];
  const firstController = new AbortController();
  const payload = { files: [{ path: "app.py" }] };
  const first = analyze(payload, firstController.signal, value => progress.push(value));
  const worker = instances[0];
  assert.equal(worker.url, "./analyzer-worker.js");
  assert.deepEqual(worker.options, { type: "module" });
  assert.deepEqual(worker.messages[0].payload, payload);
  assert.match(progress[0], /브라우저 분석기/);
  worker.reply({ routes: ["GET /items"] });
  assert.deepEqual(await first, { routes: ["GET /items"] });
  noListeners(worker);
  firstController.abort();
  assert.equal(worker.terminated, 0);
  const second = analyze({ kind: "repository", files: [] }, new AbortController().signal);
  assert.equal(instances.length, 1);
  assert.notEqual(worker.messages[0].id, worker.messages[1].id);
  worker.reply({ nodes: [] });
  assert.deepEqual(await second, { nodes: [] });
  noListeners(worker);
});

test("unrelated or late request IDs cannot settle a different analysis", async t => {
  const { analyze, instances } = await client(t);
  const promise = analyze({}, new AbortController().signal);
  const worker = instances[0];
  let settled = false;
  promise.finally(() => { settled = true; });
  worker.reply({ stale: true }, worker.messages[0].id + 1);
  worker.emit("message", { data: null });
  await Promise.resolve();
  assert.equal(settled, false);
  worker.reply({ current: true });
  assert.deepEqual(await promise, { current: true });
});

test("a successful local analysis discards its source-bearing Worker before the next analysis", async t => {
  const { analyze, instances } = await client(t);
  const controller = new AbortController();
  const first = analyze({ source: "local", kind: "repository", files: [{ path: "private.py", after: "SECRET = 1" }] }, controller.signal);
  const localWorker = instances[0];
  localWorker.reply({ nodes: [{ path: "private.py" }] });
  assert.deepEqual(await first, { nodes: [{ path: "private.py" }] });
  assert.equal(localWorker.terminated, 1);
  noListeners(localWorker);
  controller.abort();
  assert.equal(localWorker.terminated, 1);
  const next = analyze({ kind: "repository", files: [] }, new AbortController().signal);
  assert.equal(instances.length, 2);
  instances[1].reply({ nodes: [] });
  await next;
  assert.equal(instances[1].terminated, 0);
});

test("pre-aborted input rejects its reason without preparing or constructing a Worker", async t => {
  const { analyze, instances } = await client(t);
  const reason = new DOMException("User cancelled", "AbortError");
  const progress = [];
  await assert.rejects(analyze({}, AbortSignal.abort(reason), value => progress.push(value)), error => error === reason);
  assert.equal(instances.length, 0);
  assert.deepEqual(progress, []);
});

test("cancellation terminates pending Python work and a retry gets a fresh Worker", async t => {
  const { analyze, instances } = await client(t);
  const controller = new AbortController();
  const promise = analyze({}, controller.signal);
  const old = instances[0];
  const oldReceive = [...old.listeners.get("message")][0];
  const oldFailure = [...old.listeners.get("error")][0];
  const reason = new DOMException("User cancelled", "AbortError");
  const rejected = assert.rejects(promise, error => error === reason);
  controller.abort(reason);
  await rejected;
  assert.equal(old.terminated, 1);
  noListeners(old);

  const next = analyze({}, new AbortController().signal);
  const replacement = instances[1];
  oldReceive({ data: { id: old.messages[0].id, result: { stale: true } } });
  oldFailure({ message: "late error" });
  assert.equal(old.terminated, 1);
  assert.equal(replacement.terminated, 0);
  replacement.reply({ fresh: true });
  assert.deepEqual(await next, { fresh: true });
});

test("deadline reasons and falsy explicit abort reasons are rejected without changing their identity", async t => {
  const { analyze, instances } = await client(t);
  for (const reason of [new DOMException("Deadline exceeded", "TimeoutError"), null, false]) {
    const controller = new AbortController();
    const promise = analyze({}, controller.signal);
    const rejected = promise.then(() => assert.fail("Aborted work resolved"), error => assert.equal(error, reason));
    controller.abort(reason);
    await rejected;
    assert.equal(instances.at(-1).terminated, 1);
    noListeners(instances.at(-1));
  }
});

test("an abort raised during the preparation callback cannot be missed", async t => {
  const { analyze, instances } = await client(t);
  const controller = new AbortController();
  const reason = new DOMException("Cancelled during preparation", "AbortError");
  await assert.rejects(analyze({}, controller.signal, () => controller.abort(reason)), error => error === reason);
  assert.equal(instances[0].messages.length, 0);
  assert.equal(instances[0].terminated, 1);
  noListeners(instances[0]);
});

test("Worker failures remove handlers, reject once and allow a clean retry", async t => {
  const { analyze, instances } = await client(t);
  const first = analyze({}, new AbortController().signal);
  const worker = instances[0];
  const failed = [...worker.listeners.get("error")][0];
  const rejected = assert.rejects(first, /브라우저 분석기를 불러오지 못했습니다/);
  worker.emit("error", {});
  failed({});
  await rejected;
  assert.equal(worker.terminated, 1);
  noListeners(worker);
  const second = analyze({}, new AbortController().signal);
  instances[1].reply({ recovered: true });
  assert.deepEqual(await second, { recovered: true });
});

test("an analyzer error response rejects with its message and discards the failed Worker", async t => {
  const { analyze, instances } = await client(t);
  const promise = analyze({}, new AbortController().signal);
  const worker = instances[0];
  worker.emit("message", { data: { id: worker.messages[0].id, error: "invalid source payload" } });
  await assert.rejects(promise, /소스 분석을 완료하지 못했습니다\. invalid source payload/);
  assert.equal(worker.terminated, 1);
  noListeners(worker);
});

test("a synchronous postMessage failure performs the same cleanup and does not poison retries", async t => {
  const { analyze, instances, Worker } = await client(t);
  const reason = new DOMException("Payload cannot be cloned", "DataCloneError");
  Worker.postError = reason;
  await assert.rejects(analyze({}, new AbortController().signal), error => error === reason);
  assert.equal(instances[0].terminated, 1);
  noListeners(instances[0]);
  Worker.postError = undefined;
  const retry = analyze({}, new AbortController().signal);
  instances[1].reply({ recovered: true });
  assert.deepEqual(await retry, { recovered: true });
});
