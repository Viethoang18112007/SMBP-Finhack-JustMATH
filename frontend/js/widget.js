// The SSUST quick-add widget (large, on the home screen) and the full-screen camera and History
// calendar it opens inside the same phone.
//
// Type: a payment in plain words ("$50 KFC dinner"). The server reads it (assistant.parse_entry,
// offline rules), the widget shows the fund it picked and why, asks again when the amount looks
// like a typo, and Add saves it through the app's own Add flow (cover step, undo, request id).
//
// Photo: the shutter and the gallery button open the file picker (the camera on phones); the
// Samples row uses sample receipt images. Every image goes through the same real pipeline:
// offline OCR in the browser (ocr.js) -> POST /api/receipt/parse (total, merchant, fund, reason,
// typo check) -> Add payment pre-filled. A receipt is never saved by itself.

import { api } from "./api.js";
import { prefillAdd, quickAdd } from "./actions.js";
import { registerOverlay, setHtml } from "./closers.js";
import { openApp } from "./device.js";
import { CATEGORIES, FUND_NAME, escapeHtml, hk } from "./format.js";
import { readReceipt, trimText } from "./ocr.js";
import { streakChip } from "./rewards.js";
import { state } from "./store.js";

// Sample receipt images served from frontend/img/samples (fictional, marked Sample on the image).
const SAMPLES = [
  ["receipt-mcd.png", "McDonald's"],
  ["receipt-tamjai.png", "TamJai SamGor"],
  ["receipt-bookstore.png", "HKUST Bookstore"],
  ["receipt-1-noodle-bar.png", "Noodle bar"],
  ["receipt-2-cha-chaan-teng.png", "Cha chaan teng"],
  ["receipt-3-hotpot.png", "Hotpot"],
];

const w = {
  tab: "type", // "type" or "photo" (the widget's tabs)
  screen: null, // null, "camera" or "history": full screen inside the phone
  text: "",
  busy: false,
  progress: "",
  error: "",
  entry: null, // the parsed entry waiting for Add
  receipt: null, // {merchant, line, amount} when the entry came from a receipt
  done: "", // a one-line confirmation after Add
  shot: null, // the image being read or just read: {kind: "sample", src} or {kind: "picked"}
};

// The last photo picked from the gallery or the shutter, as an ImageBitmap drawn on a canvas.
// An object URL would need "blob:" in the page's img-src (the CSP allows 'self' only); a bitmap
// needs no URL. Only one is kept: the previous one is closed when a new photo replaces it.
let picked = null;

// The small widget beside it already shows what is left today: no second copy here.
function leftLine() {
  const view = state.view;
  return !view || !view.ready ? "Set your weekly budget in the app" : "Quick add";
}

function chipsHtml(entry) {
  return CATEGORIES.map(([id, name]) => {
    const on = entry.category === id;
    return `<button type="button" class="qa-chip${on ? " on" : ""}" data-w-cat="${id}" aria-pressed="${on}">${name}</button>`;
  }).join("");
}

function typoHtml(entry) {
  const typo = entry.typo;
  if (!typo) return "";
  const fix = typo.suggestion
    ? `<button type="button" class="qa-btn" data-w-amount="${typo.suggestion}">Use ${hk(typo.suggestion)}</button>`
    : "";
  return `<div class="qa-typo" role="alert"><strong>Typo?</strong> ${escapeHtml(typo.reason)}
      <div class="qa-row">${fix}<button type="button" class="qa-btn ghost" data-w-keep>Keep ${hk(entry.amount)}</button></div></div>`;
}

function resultHtml() {
  const entry = w.entry;
  if (!entry) return "";
  const receipt = w.receipt
    ? `<p class="qa-line">${w.receipt.guess ? "Best guess (largest price), check it" : "Read from the receipt"}: "${escapeHtml(w.receipt.line || "")}"${w.receipt.merchant ? ` · ${escapeHtml(w.receipt.merchant)}` : ""}</p>`
    : "";
  const sure = entry.confident ? "" : `<span class="qa-unsure">Not sure: check the fund</span>`;
  const action = w.receipt
    ? `<button type="button" class="qa-btn primary" data-w-check${entry.typo || w.busy ? " disabled" : ""}>Check in Add payment</button>`
    : `<button type="button" class="qa-btn primary" data-w-add${entry.typo || w.busy ? " disabled" : ""}>Add to SSUST</button>`;
  return `<div class="qa-result" aria-live="polite">
      ${receipt}
      <div class="qa-amtline"><span class="qa-fund">${escapeHtml(FUND_NAME[entry.category])}</span><strong class="qa-amt num">-${hk(entry.amount)}</strong></div>
      <div class="qa-note">${escapeHtml(entry.note)}</div>
      <div class="qa-why">Why: ${escapeHtml(entry.reason)} ${sure}</div>
      ${typoHtml(entry)}
      <div class="qa-chips" role="group" aria-label="Fund">${chipsHtml(entry)}</div>
      <div class="qa-row">${action}<button type="button" class="qa-btn ghost" data-close="quick">Cancel</button></div>
    </div>`;
}

function typePane() {
  return `<form class="qa-search" data-w-form>
      <input id="w-text" autocomplete="off" placeholder="$50 KFC dinner" aria-label="Type a payment, like $50 KFC dinner" value="${escapeHtml(w.text)}">
      <button type="submit" class="qa-go" aria-label="Read it">Go</button>
    </form>
`;
}

function photoPane() {
  return `<button type="button" class="qa-btn primary qa-open-cam" data-w-screen="camera">Open the camera</button>
    <p class="qa-hint">Read offline. You check it before it is saved.</p>`;
}

const ICON = {
  grid: '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="currentColor"><rect x="3" y="3" width="18" height="18" rx="5"/><g fill="#1b1b1d"><circle cx="8.5" cy="9" r="1.3"/><circle cx="12" cy="9" r="1.3"/><circle cx="15.5" cy="9" r="1.3"/><circle cx="8.5" cy="12.5" r="1.3"/><circle cx="12" cy="12.5" r="1.3"/><circle cx="15.5" cy="12.5" r="1.3"/><circle cx="8.5" cy="16" r="1.3"/><circle cx="12" cy="16" r="1.3"/></g></svg>',
  cam: '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M4 8h3l2-2.5h6L17 8h3v11H4z"/><circle cx="12" cy="13.2" r="3.4"/></svg>',
  home: '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="currentColor"><path d="M4 11 12 4l8 7v8a2 2 0 0 1-2 2h-3v-6H9v6H6a2 2 0 0 1-2-2z"/></svg>',
};

// The dark, full-screen camera: rounded viewfinder, shutter and gallery (both open the file
// picker; on a phone the shutter asks for the camera), and a row of sample receipt images.
function finderHtml() {
  const shot = w.shot;
  const reading = w.busy ? `<p class="lk-reading" role="status" id="lk-status">${escapeHtml(w.progress || "Reading the receipt…")}</p>` : "";
  if (!shot) return `<div class="lk-finder"><span class="lk-hint">Point at the total</span>${reading}</div>`;
  const image = shot.kind === "sample"
    ? `<img class="lk-shot" src="${escapeHtml(shot.src)}" alt="The receipt being read">`
    : `<canvas class="lk-shot" data-w-canvas="shot" role="img" aria-label="The photo being read"></canvas>`;
  return `<div class="lk-finder has-shot${w.entry ? " is-compact" : ""}">${image}${reading}</div>`;
}

const PHOTO_ICON = '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="3"/><circle cx="9" cy="10" r="1.6"/><path d="m4 17 5-4.5 4 3.5 3-2.5 4 3.5"/></svg>';

function cameraPane() {
  const samples = SAMPLES.map(([file, name]) => `<button type="button" class="lk-sample" data-w-sample="${file}" aria-label="Sample receipt: ${escapeHtml(name)}"><img src="img/samples/${file}" alt="" width="60" height="80"><span>${escapeHtml(name)}</span></button>`).join("");
  const thumb = picked
    ? `<canvas class="lk-thumb has-img" data-w-canvas="thumb" aria-hidden="true"></canvas>`
    : `<span class="lk-thumb" aria-hidden="true">${PHOTO_ICON}</span>`;
  return `<div class="lk-top"><button type="button" class="lk-round" data-close="camera" aria-label="Close the camera">✕</button>
      <span class="lk-pill">Scan a receipt</span><span class="lk-round lk-me" aria-hidden="true"><img src="img/icon-64.png" alt=""></span></div>
    ${!w.entry && state.data && state.data.rewards ? `<div class="lk-streak">${streakChip(state.data.rewards.streak, false)}</div>` : ""}
    ${finderHtml()}
    ${w.entry ? "" : `<div class="lk-controls">
      <label class="lk-gallery" aria-label="Pick a photo or screenshot">${thumb}<input type="file" accept="image/*" id="lk-file" data-w-file hidden></label>
      <label class="lk-shutter" aria-label="Take a photo of the receipt"><span></span><input type="file" accept="image/*" capture="environment" id="lk-shot" data-w-file hidden></label>
      <span class="lk-spacer" aria-hidden="true"></span>
    </div>
    <div class="lk-samples" role="group" aria-label="Samples"><span class="lk-samples-title">Samples</span><div class="lk-samples-row">${samples}</div></div>`}`;
}

// History: this month as a calendar, a dot per day, a receipt tile on days with payments.
function historyPane() {
  const data = state.data;
  const today = data ? data.today : new Date().toISOString().slice(0, 10);
  const [y, m] = today.split("-").map(Number);
  const first = new Date(Date.UTC(y, m - 1, 1));
  const days = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const lead = (first.getUTCDay() + 6) % 7; // Monday first
  const byDay = {};
  for (const p of (data ? data.payments : [])) byDay[p.date] = (byDay[p.date] || 0) + p.amount;
  const cells = [];
  for (let i = 0; i < lead; i += 1) cells.push('<span class="lk-cell empty"></span>');
  for (let d = 1; d <= days; d += 1) {
    const iso = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    const spent = byDay[iso];
    const now = iso === today ? " today" : "";
    cells.push(spent
      ? `<span class="lk-cell tile${now}" title="${iso}: ${hk(spent)}"><b>${d}</b><small>${hk(spent)}</small></span>`
      : `<span class="lk-cell${now}" title="${iso}"><i></i></span>`);
  }
  const month = first.toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" });
  return `<div class="lk-top"><button type="button" class="lk-round" data-close="camera" aria-label="Close History">✕</button><span class="lk-pill">History</span><span class="lk-spacer" aria-hidden="true"></span></div>
    ${data && data.rewards ? `<div class="lk-streak">${streakChip(data.rewards.streak)}</div>` : ""}
    <section class="lk-month"><h3>${escapeHtml(month)}</h3><div class="lk-grid">${cells.join("")}</div></section>
    <p class="lk-note">Days with payments this week show what you spent.</p>`;
}

function darkNav() {
  const item = (screen, icon, label) => `<button type="button" class="${w.screen === screen ? "on" : ""}" data-w-screen="${screen}" aria-label="${label}">${icon}</button>`;
  return `<nav class="lk-nav">${item("history", ICON.grid, "Receipt history")}${item("camera", ICON.cam, "Camera")}<button type="button" data-close="camera" aria-label="Home screen">${ICON.home}</button></nav>`;
}

function el(id) {
  return document.getElementById(id);
}

// The camera or History screen, over the home screen inside the phone.
function renderCamera() {
  const root = el("cam-screen");
  if (!root) return;
  const open = Boolean(w.screen);
  root.hidden = !open;
  document.body.classList.toggle("cam-open", open);
  if (!open) {
    setHtml(root, "");
    return;
  }
  const status = w.busy && w.screen !== "camera" ? `<p class="lk-note" role="status" id="lk-status">${escapeHtml(w.progress || "Reading the receipt…")}</p>` : "";
  const html = `${w.screen === "camera" ? cameraPane() : historyPane()}
      ${status}
      ${w.error ? `<p class="lk-note err" role="alert">${escapeHtml(w.error)}</p>` : ""}
      ${w.entry ? `<div class="lk-sheet qa">${resultHtml()}</div>` : darkNav()}`;
  if (!setHtml(root, html)) return;
  drawPicked(root);
  bindWidget(root);
  root.querySelector(".lk-sheet")?.scrollIntoView({ block: "end" });
}

// The large widget on the home screen. Re-drawn after every render; what is typed and the
// focus are kept.
export function renderQuick() {
  const root = el("home-quick");
  if (root) {
    const typed = el("w-text");
    const focused = typed && document.activeElement === typed;
    const caret = focused ? typed.selectionStart : null;
    if (typed) w.text = typed.value;
    const tabs = [["type", "Type"], ["photo", "Photo"]].map(([id, name]) =>
      `<button type="button" role="tab" class="${w.tab === id ? "on" : ""}" aria-selected="${w.tab === id}" data-w-tab="${id}">${name}</button>`
    ).join("");
    const inline = w.screen ? "" : `${w.busy ? `<p class="qa-hint" role="status">Reading…</p>` : ""}
        ${w.error ? `<p class="qa-error" role="alert">${escapeHtml(w.error)}</p>` : ""}
        ${resultHtml()}`;
    const html = `<div class="qa-head"><img src="img/icon-64.png" alt="" width="22" height="22"><strong>SSUST</strong><span>${escapeHtml(leftLine())}</span></div>
        <div class="qa-tabs" role="tablist" aria-label="Add by">${tabs}</div>
        ${w.tab === "type" ? typePane() : photoPane()}
        ${w.done ? `<p class="qa-done" role="status">${escapeHtml(w.done)}</p>` : ""}
        ${inline}`;
    if (setHtml(root, html)) {
      bindWidget(root);
      // A new result can be taller than the page: bring its buttons into view (inside the page).
      root.querySelector(".qa-result, .qa-done, .qa-error")?.scrollIntoView({ block: "nearest" });
    }
    const again = el("w-text");
    if (focused && again) {
      again.focus();
      again.setSelectionRange(caret, caret);
    }
  }
  renderCamera();
}

function reset() {
  w.error = "";
  w.done = "";
  w.receipt = null;
  w.entry = null;
  w.shot = null;
}

async function readText(text) {
  w.text = text;
  reset();
  w.busy = true;
  renderQuick();
  try {
    const result = await api("/api/assistant/parse", { text });
    if (result.ok) w.entry = result;
    else w.error = result.error;
  } catch (err) {
    w.error = err.message;
  }
  w.busy = false;
  renderQuick();
}

// The picked photo on each canvas that shows it (viewfinder and gallery button), scaled down.
function drawPicked(root) {
  if (!picked) return;
  root.querySelectorAll("[data-w-canvas]").forEach((canvas) => {
    const max = canvas.dataset.wCanvas === "thumb" ? 120 : 900;
    const scale = Math.min(1, max / Math.max(picked.width, picked.height));
    canvas.width = Math.max(1, Math.round(picked.width * scale));
    canvas.height = Math.max(1, Math.round(picked.height * scale));
    canvas.getContext("2d").drawImage(picked, 0, 0, canvas.width, canvas.height);
  });
}

// A photo from the gallery or the shutter becomes the one kept for the previews.
async function keepPicked(file) {
  if (typeof createImageBitmap !== "function") return false;
  try {
    const bitmap = await createImageBitmap(file);
    if (picked) picked.close();
    picked = bitmap;
    return true;
  } catch (err) {
    return false; // not an image the browser can draw: OCR still tries it
  }
}

// One image, the real pipeline: OCR on this device, then the server finds the total and the fund.
// `sample` is the path of a bundled sample (shown as is), else the file is a picked photo.
async function readImage(file, sample = null) {
  if (!file || w.busy) return;
  reset();
  w.busy = true; // also while the photo is decoded: a second tap waits
  if (sample) w.shot = { kind: "sample", src: sample };
  else if (await keepPicked(file)) w.shot = { kind: "picked" };
  w.screen = "camera";
  w.busy = true;
  w.progress = "Loading the offline reader…";
  renderQuick();
  try {
    const text = await readReceipt(file, (percent, words) => {
      w.progress = percent ? `${words}: ${percent}%` : `${words}…`;
      const status = el("lk-status");
      if (status) status.textContent = w.progress;
    });
    const result = await api("/api/receipt/parse", { text: trimText(text) });
    if (result.found && result.entry) {
      w.entry = result.entry;
      w.receipt = { merchant: result.merchant, line: result.line, amount: result.amount, guess: Boolean(result.guess) };
    } else {
      w.error = "Could not find a total on this receipt. Try another photo, or type it in.";
    }
  } catch (err) {
    w.error = "Could not read this image. Try another photo, or type it in.";
  }
  w.busy = false;
  renderQuick();
}

async function readSample(file) {
  try {
    const res = await fetch(`img/samples/${file}`);
    const blob = await res.blob();
    await readImage(new File([blob], file, { type: blob.type || "image/png" }), `img/samples/${file}`);
  } catch (err) {
    w.error = "Could not open the sample.";
    renderQuick();
  }
}

async function addEntry() {
  const entry = w.entry;
  if (!entry || entry.typo) return;
  w.busy = true;
  renderQuick();
  const saved = await quickAdd({ amount: entry.amount, category: entry.category, note: entry.note });
  w.busy = false;
  if (saved === "saved") {
    w.done = `Added: ${FUND_NAME[entry.category]} -${hk(entry.amount)} (${entry.note})`;
    w.entry = null;
    w.text = "";
    const input = el("w-text");
    if (input) input.value = "";
  } else if (saved === "confirm") {
    w.done = "More than what is left today: choose where the extra comes from in the app.";
    w.entry = null;
    openApp(null, el("home-quick"));
  } else {
    w.error = saved || "Could not add it. Try again in the app.";
  }
  renderQuick();
}

// A receipt is never saved from here: Add payment opens pre-filled and the student taps Save.
function checkEntry() {
  const entry = w.entry;
  if (!entry || entry.typo) return;
  const scan = { status: "found", guess: Boolean(w.receipt.guess), line: w.receipt.line, merchant: w.receipt.merchant, reason: entry.reason };
  // The zoom starts from the button just tapped: read its place before the camera closes.
  const from = el("cam-screen")?.querySelector("[data-w-check]")?.getBoundingClientRect();
  reset();
  w.screen = null;
  renderQuick();
  openApp(null, from || el("home-quick"));
  prefillAdd({ amount: entry.amount, category: entry.category, note: entry.note, scan });
}

function closeCamera() {
  if (w.busy) return;
  reset();
  w.screen = null;
  renderQuick();
}

function openCamera(screen = "camera") {
  w.screen = screen;
  renderQuick();
}

function bindWidget(root) {
  root.querySelector("[data-w-form]")?.addEventListener("submit", (event) => {
    event.preventDefault();
    readText(root.querySelector("#w-text").value);
  });
  root.querySelectorAll("[data-w-try]").forEach((btn) => btn.addEventListener("click", () => readText(btn.dataset.wTry)));
  root.querySelectorAll("[data-w-tab]").forEach((btn) => btn.addEventListener("click", () => {
    w.tab = btn.dataset.wTab;
    w.error = "";
    renderQuick();
  }));
  root.querySelectorAll("[data-w-screen]").forEach((btn) => btn.addEventListener("click", () => {
    if (w.busy) return;
    reset();
    openCamera(btn.dataset.wScreen);
  }));
  root.querySelectorAll("[data-w-file]").forEach((input) => input.addEventListener("change", () => readImage(input.files && input.files[0])));
  root.querySelectorAll("[data-w-sample]").forEach((btn) => btn.addEventListener("click", () => readSample(btn.dataset.wSample)));
  root.querySelectorAll("[data-w-cat]").forEach((btn) => btn.addEventListener("click", () => {
    w.entry.category = btn.dataset.wCat;
    w.entry.reason = "you picked it";
    w.entry.confident = true;
    renderQuick();
  }));
  root.querySelector("[data-w-amount]")?.addEventListener("click", (event) => {
    w.entry.amount = Number(event.currentTarget.dataset.wAmount);
    w.entry.typo = null;
    renderQuick();
  });
  root.querySelector("[data-w-keep]")?.addEventListener("click", () => {
    w.entry.typo = null;
    renderQuick();
  });
  root.querySelector("[data-w-add]")?.addEventListener("click", addEntry);
  root.querySelector("[data-w-check]")?.addEventListener("click", checkEntry);
}

function cancelEntry() {
  reset();
  renderQuick();
}

registerOverlay({ name: "camera", layer: 20, isOpen: () => Boolean(w.screen), close: closeCamera });
// Escape on a read receipt clears the result first (layer above the camera), then closes the camera.
registerOverlay({ name: "quick", layer: 25, isOpen: () => Boolean(w.entry), close: cancelEntry });
