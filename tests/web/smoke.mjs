// Smoke test for the built web page, in Node 22:  npm ci && node smoke.mjs ../../_site
//
// Loads the pinned Pyodide (npm, the same version as worker.js), installs the built wheel the way the worker does
// (micropip), runs worker.js's own read loop over a fixture folder made of File objects, and checks the summary
// against the command line's summary.json for the same folder. Prints "smoke ok".
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { loadPyodide } from "pyodide";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "../..");
const site = resolve(process.argv[2] ?? join(repo, "_site"));
const pinned = JSON.parse(readFileSync(join(here, "node_modules/pyodide/package.json"), "utf8")).version;
const work = mkdtempSync(join(tmpdir(), "skywrapped-smoke-"));

try {
  // 1. The site: built values filled in, the same Pyodide pin, and no outside requests but Pyodide and JSZip.
  const wheel = readdirSync(site).find((f) => /^skywrapped-.+-py3-none-any\.whl$/.test(f));
  assert.ok(wheel, `no skywrapped wheel in ${site}`);
  const worker = readFileSync(join(site, "worker.js"), "utf8");
  assert.equal(worker.match(/PYODIDE_VERSION = "([^"]+)"/)?.[1], pinned, "worker.js and package.json pin different Pyodides");
  assert.ok(worker.includes(`WHEEL = "${wheel}"`), "worker.js does not name the built wheel");
  const allowed = [`https://cdn.jsdelivr.net/pyodide/v${pinned}/full/`, "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/"];
  for (const name of ["index.html", "app.js", "worker.js", "style.css"]) {
    const text = readFileSync(join(site, name), "utf8");
    assert.ok(!text.includes("@@"), `${name}: an unfilled build token`);
    for (const url of text.match(/https?:\/\/[^\s"'`)]+/g) ?? []) {
      const ok = allowed.some((a) => url.startsWith(a)) ||
        url === "https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/"; // worker.js's template, pin checked above
      assert.ok(ok, `${name}: unexpected outside URL ${url}`);
    }
  }
  const index = readFileSync(join(site, "index.html"), "utf8");
  for (const copy of ["Your year under the night sky, in six cards.", "Choose your lights folder", "or drop it here",
    "Your files never leave your computer. Location is never shown.", "Tested with: ASIAIR, Celestron Origin"]) {
    assert.ok(index.includes(copy), `index.html lacks: ${copy}`);
  }

  // 2. A fixture folder like tests/conftest.py's fixture_dir, plus files the scan rules skip or cannot read.
  const lights = join(work, "lights");
  const put = (rel, bytes) => {
    mkdirSync(dirname(join(lights, rel)), { recursive: true });
    writeFileSync(join(lights, rel), bytes);
  };
  const headers = join(repo, "tests/fixtures/headers");
  for (const hdr of readdirSync(headers).filter((f) => f.endsWith(".hdr")).sort()) {
    put(`Light_${hdr.slice(0, -4)}.fit`, Buffer.concat([readFileSync(join(headers, hdr)), Buffer.alloc(2880)]));
  }
  put("._Light_asiair_2600air.fit", Buffer.alloc(4096)); // AppleDouble twin: a metadata file
  put(".DS_Store", Buffer.from("x"));
  put(".thumbs/Light_hidden.fit", readFileSync(join(headers, "asiair_4400.hdr"))); // hidden folder: never read
  put("previews/Light_asiair_2600air.jpg", Buffer.from([0xff, 0xd8]));
  put("notes.txt", Buffer.from("hello"));
  put("junk.fits", Buffer.concat([Buffer.from("GIF89a"), Buffer.alloc(5000)]));
  put("empty.fit", Buffer.alloc(0));
  put("cut.fit", readFileSync(join(headers, "asiair_2600air.hdr")).subarray(0, 4000)); // ends before its END card

  const walk = (dir) => readdirSync(dir, { withFileTypes: true }).flatMap((d) =>
    d.isDirectory() ? walk(join(dir, d.name)) : [join(dir, d.name)]);
  const entries = walk(lights).sort().map((p) => ({
    path: relative(work, p).split("\\").join("/"), // "lights/...", as webkitRelativePath gives it
    file: new File([readFileSync(p)], p.split(/[\\/]/).pop()),
  }));

  // 3. The command line's numbers for the same folder.
  const python = process.env.SKYWRAPPED_PYTHON ??
    (existsSync(join(repo, ".venv/bin/python")) ? join(repo, ".venv/bin/python") : "python3");
  const today = new Date();
  const todayIso = [today.getFullYear(), today.getMonth() + 1, today.getDate()]
    .map((n, i) => String(n).padStart(i ? 2 : 4, "0")).join("-");
  const cliSummary = (...args) => {
    const out = join(work, `cli-${args.join("")}`);
    execFileSync(python, ["-m", "skywrapped.cli", lights, "--json-only", "--out", out, ...args], { stdio: "pipe" });
    return JSON.parse(readFileSync(join(out, "summary.json"), "utf8"));
  };

  // 4. The worker's own code, with Pyodide from npm and the wheel installed by micropip.
  copyFileSync(join(site, "worker.js"), join(work, "worker.mjs"));
  const W = await import(pathToFileURL(join(work, "worker.mjs")).href);
  const engine = await W.boot(loadPyodide, `emfs:/tmp/${wheel}`, {
    beforeInstall: (py) => py.FS.writeFile(`/tmp/${wheel}`, readFileSync(join(site, wheel))),
  });
  const progress = [];
  const read = await W.readHeaders(engine, entries, (done, total) => progress.push([done, total]));
  const nFixtures = readdirSync(headers).filter((f) => f.endsWith(".hdr")).length;
  assert.equal(read, nFixtures + 3, "files read: every header fixture + junk, empty, cut");
  assert.deepEqual(progress.at(-1), [read, read]);

  // Moon phase comes from trig that differs in the last digits between Pyodide's wasm and native Python.
  const norm = (sum) => ({ ...sum, per_night: sum.per_night.map((n) => ({ ...n, moon: Math.round(n.moon * 1e9) / 1e9 })) });
  const year = 2026; // the fixtures are 2026 nights
  const web = W.finish(engine, { year, tz: -5, today: todayIso, theme: "observatory" });
  assert.deepEqual(norm(web.summary), norm(cliSummary("--year", String(year), "--tz", "-5")));
  assert.equal(web.summary.skipped.unreadable, 3);
  assert.equal(web.summary.skipped.metadata_file, 1);
  assert.equal(web.summary.skipped.calibration, 2);

  const all = W.finish(engine, { year: null, tz: 0, today: todayIso, theme: "observatory" });
  assert.deepEqual(norm(all.summary), norm(cliSummary("--all", "--tz", "0")));

  const neb = W.rerender(engine, "nebula");
  assert.deepEqual(neb.summary, all.summary);
  assert.deepEqual(neb.cards.map((c) => [c.name, c.stem, c.width, c.height]),
    all.cards.map((c) => [c.name, c.stem, c.width, c.height]));
  assert.ok(neb.cards.every((c, i) => c.svg !== all.cards[i].svg && c.svg.startsWith("<svg")));

  const text = JSON.stringify([web, all, neb]);
  for (const secret of ["12.3456", "65.4321", "Light_", "lights/", work]) {
    assert.ok(!text.includes(secret), `output contains ${secret}`);
  }
  console.log("smoke ok");
} finally {
  rmSync(work, { recursive: true, force: true });
}
