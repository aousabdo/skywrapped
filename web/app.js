// The page: pick or drop a folder, hand the File handles to the worker, show the cards, save them as PNGs.
// Only counts are ever shown: never a file or folder name, a site, or raw OBJECT text.

const JSZIP = {
  src: "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js",
  integrity: "sha512-XMVd28F1oH/O71fzwBnV7HucLxVwtxf26XV8P4wPk26EDxuGZ91N8bsOttmnomcCD3CS5ZMRL50H0GgOHvegtg==",
};
const FIRST_YEAR = 2000;

const $ = (id) => document.getElementById(id);
const html = document.documentElement;
// sent: the options of the last request, so controls changed while the worker was busy are caught up afterwards
const state = { busy: false, scanned: false, result: null, urls: new Map(), sent: null };

const int = (n) => Number(n).toLocaleString("en-US");
const plural = (n, one, many) => `${int(n)} ${n === 1 ? one : many}`;
const hours = (h) => (h >= 10 ? int(Math.round(h)) : (Math.round(h * 10) / 10).toFixed(1));

function localToday() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function setStatus(text) {
  $("status").textContent = text;
}

// ---------------------------------------------------------------- options

function zoneLabel(h) {
  if (h === 0) return "UTC±0";
  const m = Math.round(Math.abs(h) * 60);
  const hh = Math.floor(m / 60);
  const mm = m % 60;
  return `UTC${h < 0 ? "−" : "+"}${hh}${mm ? `:${String(mm).padStart(2, "0")}` : ""}`;
}

function fillOptions() {
  const year = $("year");
  const now = new Date().getFullYear();
  for (let y = now; y >= FIRST_YEAR; y--) year.add(new Option(String(y), String(y)));
  year.add(new Option("All years", "all"));
  year.value = String(now);

  const tz = $("tz");
  const local = -new Date().getTimezoneOffset() / 60; // getTimezoneOffset is minutes BEHIND UTC
  const zones = [];
  for (let q = -48; q <= 56; q++) zones.push(q / 4);
  if (!zones.includes(local)) zones.push(local);
  zones.sort((a, b) => a - b);
  for (const h of zones) tz.add(new Option(h === local ? `${zoneLabel(h)} (this computer)` : zoneLabel(h), String(h)));
  tz.value = String(local);
}

function options() {
  const y = $("year").value;
  return {
    year: y === "all" ? null : Number(y),
    tz: Number($("tz").value),
    today: localToday(),
    theme: document.querySelector('input[name="theme"]:checked').value,
  };
}

// ---------------------------------------------------------------- the worker

const worker = new Worker("worker.js", { type: "module" });
html.dataset.engine = "loading";

worker.onmessage = ({ data }) => {
  if (data.type === "ready") onReady();
  else if (data.type === "progress") onProgress(data);
  else if (data.type === "result") onResult(data);
  else if (data.type === "error") onError(data);
};
worker.onerror = (event) => {
  event.preventDefault();
  onError({ code: "load" });
};

function onReady() {
  html.dataset.engine = "ready";
  if (!state.busy && !state.scanned) setStatus("");
}

function onProgress({ done, total }) {
  $("progress").max = Math.max(total, 1);
  $("progress").value = done;
  setStatus(`Reading headers: ${int(done)} of ${plural(total, "file", "files")}`);
}

function busy(on) {
  state.busy = on;
  $("choose").disabled = on;
  $("drop").classList.toggle("is-busy", on);
  $("progress-wrap").hidden = !on;
}

function scan(entries) {
  if (state.busy) return;
  if (html.dataset.engine === "failed") {
    onError({ code: "load" });
    return;
  }
  if (!entries.length) {
    setStatus("That folder is empty.");
    return;
  }
  busy(true);
  $("progress").removeAttribute("value"); // indeterminate until the first count
  $("results").hidden = true;
  state.scanned = false;
  state.result = null;
  setStatus(html.dataset.engine === "ready" ? "Reading headers…" : "Getting ready: the first visit loads Python into this page…");
  state.sent = options();
  worker.postMessage({ type: "scan", entries: unique(entries), options: state.sent });
}

function refinish() {
  if (!state.scanned || state.busy) return;
  state.sent = options();
  worker.postMessage({ type: "finish", options: state.sent });
}

function retheme() {
  if (!state.result || state.busy) return;
  const { theme } = options();
  state.sent = { ...state.sent, theme };
  worker.postMessage({ type: "theme", theme });
}

// After a result: if the year, time zone or look were changed while it was being made, make it again.
function catchUp() {
  if (!state.scanned || !state.sent) return;
  const now = options();
  if (now.year !== state.sent.year || now.tz !== state.sent.tz) refinish();
  else if (now.theme !== state.sent.theme) retheme();
}

// ---------------------------------------------------------------- picking and dropping

function unique(entries) {
  const seen = new Set();
  return entries.map(({ path, file }) => {
    let p = path;
    for (let n = 2; seen.has(p); n++) p = `copy${n}/${path}`; // two dropped folders with one name
    seen.add(p);
    return { path: p, file };
  });
}

function fromPicker(files) {
  return Array.from(files, (file) => ({ path: file.webkitRelativePath || file.name, file }));
}

// Must be called inside the drop event: the DataTransfer is emptied once the handler returns.
async function fromDrop(dataTransfer) {
  const roots = Array.from(dataTransfer.items, (item) => item.webkitGetAsEntry?.()).filter(Boolean);
  if (!roots.length) return fromPicker(dataTransfer.files); // no entries API: the dropped files themselves
  const out = [];
  const asFile = (entry) => new Promise((resolve) => entry.file(resolve, () => resolve(null)));
  const readAll = async (dir) => {
    const reader = dir.createReader();
    const all = [];
    for (;;) {
      const batch = await new Promise((resolve) => reader.readEntries(resolve, () => resolve([])));
      if (!batch.length) return all;
      all.push(...batch);
    }
  };
  const walk = async (entry) => {
    if (entry.isFile) {
      const file = await asFile(entry);
      if (file) out.push({ path: entry.fullPath.replace(/^\/+/, ""), file });
    } else if (entry.isDirectory) {
      await Promise.all((await readAll(entry)).map(walk));
    }
  };
  await Promise.all(roots.map(walk));
  return out;
}

// ---------------------------------------------------------------- results

const SKIPPED = [
  ["calibration", "calibration frame", "calibration frames"],
  ["not_light", "frame typed as something other than a light", "frames typed as something other than a light"],
  ["duplicate", "duplicate copy", "duplicate copies"],
  ["stack_with_subs", "stack whose subs are counted", "stacks whose subs are counted"],
  ["outside_year", "frame from another year", "frames from other years"],
  ["no_time", "frame without a time", "frames without a time"],
  ["unreadable", "unreadable file", "unreadable files"],
  ["metadata_file", "macOS metadata file", "macOS metadata files"],
  ["excluded", "excluded file", "excluded files"],
];

function onResult(data) {
  busy(false);
  if (data.error) {
    onError({ code: data.error, ...data });
    catchUp();
    return;
  }
  state.scanned = true;
  state.result = data;
  const s = data.summary;
  $("totals").textContent = `${hours(s.hours)} hours · ${plural(s.nights, "night", "nights")} · ` +
    `${plural(s.frames, "frame", "frames")} · ${plural(s.targets, "target", "targets")}`;
  const skipped = SKIPPED.filter(([k]) => s.skipped[k]).map(([k, one, many]) => plural(s.skipped[k], one, many));
  const notes = [];
  if (skipped.length) notes.push(`Not counted: ${skipped.join(", ")}.`);
  if (s.skipped.type_assumed) notes.push(`${plural(s.skipped.type_assumed, "frame", "frames")} had no frame type and counted as lights.`);
  if (s.night_boundaries_estimated) notes.push("Night boundaries were estimated from the frame times.");
  $("skipped").textContent = notes.join(" ");
  showCards(data.cards);
  $("results").hidden = false;
  setStatus(s.partial ? `Done: ${s.year} so far.` : "Done.");
  catchUp();
}

function cardLabel(card, i, n) {
  return card.name === "poster" ? "Poster: the year on one wide card" : `Card ${i + 1} of ${n}: ${card.name}`;
}

function showCards(cards) {
  for (const url of state.urls.values()) URL.revokeObjectURL(url);
  state.urls.clear();
  const box = $("cards");
  box.replaceChildren();
  const portrait = cards.filter((c) => c.name !== "poster").length;
  cards.forEach((card, i) => {
    const url = URL.createObjectURL(new Blob([card.svg], { type: "image/svg+xml" }));
    state.urls.set(card.stem, url);
    const fig = document.createElement("figure");
    fig.className = card.name === "poster" ? "card wide" : "card";
    const img = new Image(card.width, card.height);
    img.src = url;
    img.alt = cardLabel(card, i, portrait);
    img.decoding = "async";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ghost";
    btn.textContent = `Download ${card.stem}.png`;
    btn.addEventListener("click", () => withButton(btn, async () => save(await png(card), `${card.stem}.png`)));
    fig.append(img, btn);
    box.append(fig);
  });
}

async function png(card) {
  const img = new Image();
  img.src = state.urls.get(card.stem);
  await img.decode();
  const canvas = document.createElement("canvas");
  canvas.width = card.width;
  canvas.height = card.height;
  canvas.getContext("2d").drawImage(img, 0, 0, card.width, card.height);
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("toBlob failed"))), "image/png"));
}

function save(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 30000);
}

async function withButton(btn, job) {
  const text = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Saving…";
  try {
    await job();
  } catch {
    console.error("skywrapped: a download failed"); // a fixed text: an error message could hold a file name
    setStatus("That download did not work. Try again, or use another browser.");
  } finally {
    btn.disabled = false;
    btn.textContent = text;
  }
}

let jszip;
function loadJsZip() {
  jszip ??= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = JSZIP.src;
    s.integrity = JSZIP.integrity;
    s.crossOrigin = "anonymous";
    s.referrerPolicy = "no-referrer";
    s.onload = () => (window.JSZip ? resolve(window.JSZip) : reject(new Error("JSZip missing")));
    s.onerror = () => {
      jszip = undefined;
      reject(new Error("JSZip did not load"));
    };
    document.head.append(s);
  });
  return jszip;
}

async function downloadAll() {
  if (!state.result) return;
  const { summary, cards } = state.result;
  const JSZip = await loadJsZip();
  const zip = new JSZip();
  for (const card of cards) {
    zip.file(`${card.stem}.png`, await png(card));
    zip.file(`${card.stem}.svg`, card.svg);
  }
  zip.file("summary.json", JSON.stringify(summary, null, 2));
  save(await zip.generateAsync({ type: "blob" }), `skywrapped-${summary.year ?? "all"}.zip`);
}

// ---------------------------------------------------------------- errors (counts only)

function onError(data) {
  busy(false);
  if (data.code === "load") {
    html.dataset.engine = "failed";
    setStatus("The page could not load its reader. Check your connection and reload.");
  } else if (data.code === "no_files") {
    setStatus(`No FITS or XISF light frames here (looked at ${plural(data.looked, "file", "files")}).`);
  } else if (data.code === "no_lights") {
    const year = state.sent ? state.sent.year : options().year; // the year this result was made for
    const read = `read ${plural(data.headers, "header", "headers")}` +
      (data.skipped?.unreadable ? `, ${plural(data.skipped.unreadable, "file", "files")} unreadable` : "");
    let text = `No light frames to count${year ? ` in ${year}` : ""} (${read}).`;
    if (data.years?.length) text += ` Lights found in ${data.years.join(", ")}: choose it under Year.`;
    state.scanned = data.headers > 0; // another year can still be counted without reading again
    state.result = null;
    $("results").hidden = true;
    setStatus(text);
  } else {
    setStatus("Something went wrong reading these files. Reload the page and try again.");
  }
}

// ---------------------------------------------------------------- wiring

fillOptions();
setStatus("Getting ready…");

$("choose").addEventListener("click", () => $("folder").click());
$("folder").addEventListener("change", (e) => {
  const entries = fromPicker(e.target.files);
  e.target.value = "";
  scan(entries);
});

const drop = $("drop");
for (const type of ["dragover", "drop"]) window.addEventListener(type, (e) => e.preventDefault());
drop.addEventListener("dragenter", () => drop.classList.add("is-over"));
drop.addEventListener("dragover", (e) => {
  e.dataTransfer.dropEffect = state.busy ? "none" : "copy";
  drop.classList.add("is-over");
});
drop.addEventListener("dragleave", (e) => {
  if (!drop.contains(e.relatedTarget)) drop.classList.remove("is-over");
});
drop.addEventListener("drop", async (e) => {
  drop.classList.remove("is-over");
  if (state.busy) return;
  setStatus("Listing the files…");
  scan(await fromDrop(e.dataTransfer));
});

$("year").addEventListener("change", refinish);
$("tz").addEventListener("change", refinish);
for (const radio of document.querySelectorAll('input[name="theme"]')) radio.addEventListener("change", retheme);
$("download-all").addEventListener("click", (e) => withButton(e.currentTarget, downloadAll));
