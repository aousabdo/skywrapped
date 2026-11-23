// The page's Web Worker: Python (Pyodide) running the skywrapped wheel over header slices.
//
// It is given File handles and reads only each file's first bytes (FIRST_READ, then more only when a header asks
// for it). Nothing is sent anywhere: the only requests are Pyodide from jsDelivr and the wheel from this site.
// tests/web/smoke.mjs imports this module and runs the same functions in Node.

export const PYODIDE_VERSION = "314.0.8"; // tests/web/package.json pins the same version
export const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
export const WHEEL = "@@WHEEL@@"; // filled in by scripts/build_web.py
export const BATCH = 200;

// Pyodide, micropip and the wheel; resolves to the engine the other functions take.
export async function boot(loadPyodide, wheelUrl, { pyodide = {}, beforeInstall } = {}) {
  const py = await loadPyodide(pyodide);
  if (beforeInstall) await beforeInstall(py);
  await py.loadPackage("micropip", { messageCallback: () => {} });
  const micropip = py.pyimport("micropip");
  await micropip.install(wheelUrl);
  micropip.destroy();
  const api = py.pyimport("skywrapped.web_api");
  return { py, api, firstRead: api.FIRST_READ };
}

async function slice(file, n) {
  try {
    return new Uint8Array(await file.slice(0, n).arrayBuffer());
  } catch {
    return new Uint8Array(0); // a file that can no longer be read: web_api counts it as unreadable
  }
}

function call(engine, fn, ...args) {
  const pyArgs = args.map((a) => (a !== null && typeof a === "object" ? engine.py.toPy(a) : a));
  try {
    const out = fn(...pyArgs);
    if (out && typeof out.toJs === "function") {
      const js = out.toJs();
      out.destroy();
      return js;
    }
    return out;
  } finally {
    for (const a of pyArgs) if (a && typeof a.destroy === "function") a.destroy();
  }
}

// entries: [{path, file}] with browser relative paths. Reads the headers of the files web_api selects, BATCH at a
// time, re-slicing only the files whose header needs more bytes. Returns how many files were read.
export async function readHeaders(engine, entries, onProgress = () => {}) {
  const { api } = engine;
  api.reset();
  const keep = Array.from(call(engine, api.select, entries.map((e) => e.path)));
  const todo = keep.map((i) => entries[i]);
  const files = new Map(todo.map((e) => [e.path, e.file]));
  onProgress(0, todo.length);
  for (let i = 0; i < todo.length; i += BATCH) {
    let ask = todo.slice(i, i + BATCH).map((e) => [e.path, engine.firstRead]);
    while (ask.length) {
      const items = await Promise.all(ask.map(async ([path, n]) => [path, await slice(files.get(path), n)]));
      ask = call(engine, engine.api.parse_batch, items);
    }
    onProgress(Math.min(i + BATCH, todo.length), todo.length);
  }
  return todo.length;
}

// {year (null = all years), tz (hours east of UTC), today ("YYYY-MM-DD"), theme} -> {summary, cards} or {error}
export function finish(engine, { year, tz, today, theme }) {
  // JS undefined arrives in Python as None (null would arrive as JsNull)
  return JSON.parse(engine.api.finish(year ?? undefined, tz, today, theme));
}

export function rerender(engine, theme) {
  return JSON.parse(engine.api.rerender(theme));
}

// ---------------------------------------------------------------- the worker itself
// Console messages are fixed texts: a Python error message could hold a file name.

if (typeof WorkerGlobalScope !== "undefined" && self instanceof WorkerGlobalScope) {
  const ready = (async () => {
    const { loadPyodide } = await import(`${PYODIDE_URL}pyodide.mjs`);
    return boot(loadPyodide, new URL(WHEEL, self.location.href).href, { pyodide: { indexURL: PYODIDE_URL } });
  })();
  ready.then(
    () => self.postMessage({ type: "ready" }),
    () => {
      console.error("skywrapped: the header reader could not start");
      self.postMessage({ type: "error", code: "load" });
    },
  );

  // Messages run one after another, so a theme switch never interleaves with a scan.
  let queue = Promise.resolve();
  self.onmessage = (event) => {
    queue = queue.then(() => handle(event.data));
  };

  async function handle(msg) {
    let engine;
    try {
      engine = await ready;
    } catch {
      return; // the load error was posted already
    }
    try {
      if (msg.type === "scan") {
        const files = await readHeaders(engine, msg.entries, (done, total) =>
          self.postMessage({ type: "progress", done, total }),
        );
        if (files === 0) {
          self.postMessage({ type: "error", code: "no_files", looked: msg.entries.length });
          return;
        }
        self.postMessage({ type: "result", ...finish(engine, msg.options) });
      } else if (msg.type === "finish") {
        self.postMessage({ type: "result", ...finish(engine, msg.options) });
      } else if (msg.type === "theme") {
        self.postMessage({ type: "result", ...rerender(engine, msg.theme) });
      }
    } catch {
      console.error("skywrapped: reading the headers failed");
      self.postMessage({ type: "error", code: "internal" });
    }
  }
}
