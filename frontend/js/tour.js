// The guided tour and the auto-play demo.
//
// Guided: the person moves with Next / Back through STEPS (tour-steps.js). It only switches
// screens, it never saves anything, so it is safe in LIVE too.
//
// Auto-play (DEMO only) follows TIMELINE (demo-timeline.js): every step has an absolute start
// and end time and actions at exact offsets. One clock drives it all: elapsed time comes from
// performance.now() against one start time, read on every animation frame, so steps never drift
// (no chain of timeouts adding up). An action that is late is logged (demoLog). The actions
// really use the app: they click the same buttons a person would (Save, the modal's Confirm,
// Undo), so request ids, the confirm guard and every animation are the real ones. Next / Back /
// Restart jump to the exact start of a step: the demo is reset and the step's setup rebuilds the
// state it starts from, then the clock is set to that time. The demo is reset before it starts and
// again when it ends, is skipped, or fails, so every run is the same. Skip, Pause and Escape are
// never blocked. A small m:ss timer shows in a corner (hidden with ?timer=0).
//
// For a screen recording, ?record=1 (or ?cursor=1 for the pointer alone) shows a pointer that
// glides to each control and clicks (cursor.js) before the same real click happens. Record mode
// keeps the captions as subtitles and hides the buttons, the step counter and the timer.

import { closeAdd, closeSheet, setConnected, simulateTap, switchMode } from "./actions.js";
import { aimAt, clickEffect, cursorOn, cursorWanted, follow, hideCursor, moveTo, press, recordMode, showCursor, showRecordHint } from "./cursor.js";
import { TIMELINE } from "./demo-timeline.js";
import { goToPage, isFramed, onHome, openApp, showHome } from "./device.js";
import { resetTaps } from "./inbox.js";
import { fire as fireNote, openCenter, resetNotifications, setAutoNotify } from "./notifications.js";
import { prefersReducedMotion, tokenMs } from "./motion.js";
import { render } from "./render.js";
import { trapFocus } from "./sheet.js";
import { setFundView, state } from "./store.js";
import { STEPS } from "./tour-steps.js";

export const STEP_MIN_MS = 4000;
export const STEP_MAX_MS = 7000;
export const BASE_MS = 2000;
export const MS_PER_CHAR = 22;
const RUNNING_KEY = "ssust.autoplayRunning"; // session: set while auto-play runs, to recover after a reload
const OFFER_KEY = "ssust.tourOffer"; // local: "off" after "Skip"
const OFFER_SEEN_KEY = "ssust.tourOfferSeen"; // session: the demo or the tour was started

// Pure parts ---------------------------------------------------------------------------------

// Auto-play only ever runs in DEMO: it saves payments, so it must never touch LIVE data.
export function canAutoplay(mode) {
  return mode === "demo";
}

// How long an auto-play step stays: by text length, between 4 and 7 seconds.
export function stepDuration(step, auto = true) {
  const text = step.title + (auto && step.autoBody ? step.autoBody : step.body);
  return Math.min(STEP_MAX_MS, Math.max(STEP_MIN_MS, BASE_MS + MS_PER_CHAR * text.length));
}

export function stepsFor(mode) {
  if (mode === "auto") return TIMELINE;
  return STEPS.filter((step) => !step.autoOnly);
}

// "m:ss" for a number of seconds.
export function clockText(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// Where the bubble goes: next to the target on the preferred side if it fits, else another
// side, else over the bottom of the viewport (no arrow). Always inside the viewport.
export function placeBubble(target, size, viewport, preferred = "auto", gap = 14, margin = 8) {
  const clampX = (x) => Math.min(Math.max(x, margin), Math.max(margin, viewport.w - size.w - margin));
  const clampY = (y) => Math.min(Math.max(y, margin), Math.max(margin, viewport.h - size.h - margin));
  if (!target || preferred === "center") {
    return { x: clampX((viewport.w - size.w) / 2), y: clampY((viewport.h - size.h) / 2), side: "center", arrow: null };
  }
  const cx = target.x + target.w / 2;
  const cy = target.y + target.h / 2;
  const sides = {
    bottom: { x: clampX(cx - size.w / 2), y: target.y + target.h + gap, fits: target.y + target.h + gap + size.h <= viewport.h - margin },
    top: { x: clampX(cx - size.w / 2), y: target.y - gap - size.h, fits: target.y - gap - size.h >= margin },
    right: { x: target.x + target.w + gap, y: clampY(cy - size.h / 2), fits: target.x + target.w + gap + size.w <= viewport.w - margin },
    left: { x: target.x - gap - size.w, y: clampY(cy - size.h / 2), fits: target.x - gap - size.w >= margin },
  };
  const side = [preferred, "bottom", "top", "right", "left"].find((name) => sides[name] && sides[name].fits);
  if (!side) return { x: clampX((viewport.w - size.w) / 2), y: clampY(viewport.h - size.h - margin), side: "over", arrow: null };
  const spot = sides[side];
  const arrow = side === "top" || side === "bottom"
    ? Math.min(Math.max(cx - spot.x, 18), size.w - 18)
    : Math.min(Math.max(cy - spot.y, 18), size.h - 18);
  return { x: spot.x, y: spot.y, side, arrow };
}

// Storage that may be missing or blocked: never throws.
function storageGet(kind, key) {
  try {
    return window[kind].getItem(key);
  } catch (err) {
    return null;
  }
}

function storageSet(kind, key, value) {
  try {
    if (value == null) window[kind].removeItem(key);
    else window[kind].setItem(key, value);
  } catch (err) {
    // the tour works the same without storage
  }
}

// Waiting on the app ---------------------------------------------------------------------------

let tour = null;

class Stopped extends Error {}

function alive(token) {
  return Boolean(tour && tour.token === token && !tour.ending);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function visible(el) {
  return Boolean(el && el.getClientRects().length && !el.closest("[hidden]"));
}

// The element for `selector` once it is on screen. Stops the run if the app shows an error
// (an API call failed) or if the tour was skipped meanwhile.
async function need(selector, token, timeout = 5000) {
  const end = performance.now() + timeout;
  for (;;) {
    if (!alive(token)) throw new Stopped();
    if (tour.mode === "auto" && state.error) throw new Error(state.error);
    const el = document.querySelector(selector);
    if (visible(el)) return el;
    if (performance.now() > end) throw new Error(`missing ${selector}`);
    await sleep(50);
  }
}

async function until(test, token, timeout = 5000) {
  const end = performance.now() + timeout;
  while (!test()) {
    if (!alive(token)) throw new Stopped();
    if (tour.mode === "auto" && state.error) throw new Error(state.error);
    if (performance.now() > end) throw new Error("timeout");
    await sleep(50);
  }
}

// The pointer is on and may move: never while a step's setup rebuilds the state (seeking).
function pointing() {
  return Boolean(cursorOn() && tour && !tour.seeking);
}

// True when the app (not the caption overlay or the pointer) shows `el` at that point: the
// sticky header, the Add button or the tab bar may cover a part of the scrolling screen.
function shownAt(el, point) {
  const hit = document.elementsFromPoint(point.x, point.y)
    .find((e) => !e.closest("#tour") && !e.closest(".ghost-cursor"));
  return Boolean(hit && (hit === el || el.contains(hit) || hit.contains(el)));
}

// Bring an element into view only if too little of it shows, or if something covers its middle.
async function ensureVisible(el, token) {
  const shown = () => {
    const r = el.getBoundingClientRect();
    const v = visibleRect(el);
    return r.width * r.height > 0 && v.w * v.h >= 0.6 * r.width * r.height && shownAt(el, aimAt(el));
  };
  if (shown()) return;
  // Only the list that scrolls it moves: scrollIntoView would also scroll the phone frame
  // (overflow hidden) and push the whole phone out of place.
  const box = scrollerOf(el);
  if (!box) return;
  const delta = () => {
    const r = el.getBoundingClientRect();
    const b = box.getBoundingClientRect();
    return Math.round(r.top + r.height / 2 - (b.top + b.height / 2));
  };
  box.scrollBy({ top: delta(), behavior: prefersReducedMotion() ? "auto" : "smooth" });
  await settleScroll(el, token);
  if (!shown() && Math.abs(delta()) > 2) box.scrollBy({ top: delta() }); // a slow frame cut the smooth scroll short
}

function scrollerOf(el) {
  for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
    if (/(auto|scroll)/.test(getComputedStyle(p).overflowY) && p.scrollHeight > p.clientHeight + 1) return p;
  }
  return null;
}

// Waits until the element stops moving (a smooth scroll ended), at most about 1.6 s: a long
// list scrolls for more than a second.
async function settleScroll(el, token) {
  const end = performance.now() + 1600;
  let last = null;
  let still = 0;
  while (performance.now() < end) {
    await sleep(40);
    if (!alive(token)) throw new Stopped();
    const r = el.getBoundingClientRect();
    if (last && Math.abs(r.top - last.top) < 0.5 && Math.abs(r.left - last.left) < 0.5) {
      if (++still >= 3) return;
    } else {
      still = 0;
    }
    last = r;
  }
}

// A click on a real control. With the pointer: glide there and show the click first.
async function pressEl(target, token) {
  if (pointing()) {
    // The app zooms in from the home screen: aim once it is at full size (at most 600 ms).
    const phone = document.getElementById("phone");
    const end = performance.now() + 600;
    while (phone && phone.classList.contains("app-zoom") && performance.now() < end) await sleep(40);
    if (!alive(token)) throw new Stopped();
    await ensureVisible(target, token);
    if (!alive(token)) throw new Stopped();
    await moveTo(target);
    if (!alive(token)) throw new Stopped();
    await clickEffect();
    if (!alive(token)) throw new Stopped();
  }
  target.click();
}

// Text into a field. With the pointer: click it, then one character every 65 ms.
async function typeText(input, text, token) {
  if (!pointing()) {
    input.value = text;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    return input;
  }
  await pressEl(input, token);
  const field = () => (input.isConnected ? input : document.getElementById(input.id)) || input;
  field().focus({ preventScroll: true });
  field().value = "";
  for (let i = 1; i <= text.length; i++) {
    await sleep(65);
    if (!alive(token)) throw new Stopped();
    const el = field();
    el.value = text.slice(0, i);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }
  return field();
}

function settleMs() {
  return prefersReducedMotion() ? 30 : tokenMs("--dur-base", 220) + 60;
}

function assertDemo() {
  if (!state.data || !canAutoplay(state.data.mode)) {
    const err = new Error("left demo");
    err.userMessage = "The demo stopped because the app left DEMO mode. Your LIVE data was not touched.";
    throw err;
  }
}

// Screens, the same way a person gets there. "add" is the Add sheet, opened from Today.
// "home" is the simulated home screen (phone view only; on a real phone width it is a no-op and
// the step pointing at it is skipped).
async function goScreen(name, token) {
  if (!name) return;
  if (name === "home") {
    if (state.sheet) closeSheet();
    if (state.adding) closeAdd();
    const bar = document.getElementById("home-bar");
    if (pointing() && !onHome() && visible(bar)) await pressEl(bar, token);
    showHome();
    goToPage(0, false); // the widgets page
    await sleep(settleMs());
    return;
  }
  if (onHome()) {
    const widget = document.querySelector('#home .widget.small[data-open-app="today"]');
    if (pointing() && visible(widget)) await pressEl(widget, token);
    if (onHome()) openApp(null);
  }
  if (state.sheet) closeSheet();
  if (name === "add") {
    if (!state.adding) {
      await goScreen("today", token);
      const add = document.getElementById("add");
      if (add) await pressEl(add, token);
    }
  } else {
    if (state.adding) closeAdd();
    const tab = document.querySelector(`#nav [data-screen="${name}"]`);
    if (state.screen !== name && tab) await pressEl(tab, token);
  }
  if (name === "map") await need("#osm-map, #screen .explain", token, 8000);
  await sleep(settleMs());
}

// The scripted DEMO story. Each one clicks the real controls and waits for the app to answer.
const ACTIONS = {
  async showTanks(token) {
    await goScreen("today", token);
    const button = await need('[data-fund-view="tanks"]', token);
    if (state.fundView !== "tanks") button.click();
    await need(".tanks", token);
    await sleep(settleMs());
  },
  async typeAmount(token) {
    await goScreen("add", token);
    await typeText(await need("#amount", token), "160", token);
    await sleep(settleMs());
  },
  async openCover(token) {
    if (!(await need("#amount", token)).value) throw new Error("no amount");
    await pressEl(await need("#save", token), token);
    await need("#sheet .options", token);
    await sleep(tokenMs("--dur-slow", 360));
  },
  async pickFlex(token) {
    await pressEl(await need('#sheet input[value="flex"]', token), token);
    await sleep(settleMs());
  },
  async confirm(token) {
    await pressEl(await need("#confirm-cover", token), token);
    await need("[data-undo]", token);
    await until(() => !state.saving && !state.sheet, token);
    await sleep(tokenMs("--dur-count", 500));
  },
  // The quick-add widget on the home screen: type in plain words, read the fund, then Add (the
  // normal Add flow saves it). Phone view only: on a real phone width the step is skipped.
  async quickAdd(token) {
    await goScreen("home", token);
    if (!isFramed()) return;
    if (!document.getElementById("w-text")) await pressEl(await need('[data-w-tab="type"]', token), token);
    const input = await typeText(await need("#w-text", token), "$50 KFC dinner", token);
    input.closest("form").requestSubmit();
    await need("[data-w-add]:not([disabled])", token);
    await sleep(pointing() ? 900 : settleMs()); // time to read the picked fund
    await pressEl(await need("[data-w-add]:not([disabled])", token), token);
    await need(".qa-done", token);
    await until(() => !state.saving, token);
    await sleep(tokenMs("--dur-count", 500));
  },
  // The bundled sample receipt goes through the real file input, like a picked photo.
  async scanSample(token) {
    await goScreen("add", token);
    await need("#scan-btn", token);
    const input = document.getElementById("scan-file");
    const img = new Image();
    img.src = "img/samples/receipt-1-noodle-bar.png";
    await img.decode();
    const canvas = document.createElement("canvas");
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    canvas.getContext("2d").drawImage(img, 0, 0);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    const files = new DataTransfer();
    files.items.add(new File([blob], "receipt-1-noodle-bar.png", { type: "image/png" }));
    input.files = files.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
    await until(() => state.scan && state.scan.status !== "reading", token, 45000);
    await sleep(settleMs());
  },
  // Settings > Connected payments: switch Apple Wallet on, then simulate a tap (sample payment).
  async simulateTap(token) {
    await goScreen("settings", token);
    const sw = await need('[data-connect="apple_pay"]', token);
    if (sw.getAttribute("aria-pressed") !== "true") sw.click();
    (await need('#connected-card [data-tap="apple_pay"]', token)).click();
    await need("#notify .notify-card", token);
    await sleep(settleMs());
  },
  async openReview(token) {
    const note = document.querySelector("#notify:not([hidden]) [data-notify-open]");
    if (note) note.click();
    else await goScreen("today", token);
    await need("#review-card", token);
    await sleep(settleMs());
  },
  async confirmReview(token) {
    await pressEl(await need("[data-review-confirm]", token), token);
    await until(() => !state.saving && !state.sheet && !(state.data.inbox || []).length, token);
    await sleep(tokenMs("--dur-count", 500));
    await goScreen("home", token);
  },
  async undo(token) {
    await pressEl(await need("[data-undo]", token), token);
    await pressEl(await need("[data-undo-yes]", token), token);
    await until(() => !state.saving && !document.querySelector("[data-undo]"), token);
    await sleep(tokenMs("--dur-count", 500));
  },
};

// The timeline's actions (demo-timeline.js "do"). Each one uses the real UI, like ACTIONS.
const TIMELINE_ACTIONS = {
  async show(token, a) {
    await goScreen(a.screen, token);
  },
  async scrollTo(token, a) {
    const el = await need(a.selector, token);
    el.scrollIntoView({ block: a.block || "start", behavior: prefersReducedMotion() ? "auto" : "smooth" });
    await sleep(settleMs());
    if (pointing()) {
      await settleScroll(el, token);
      // Point at what the caption talks about: `aim` (a selector inside, like the amount), else
      // the top of the element.
      const aim = a.aim ? document.querySelector(a.aim) : null;
      const target = aim && visible(aim) ? aim : el;
      const v = visibleRect(target);
      if (v.w > 0 && v.h > 0) await moveTo(aimAt(target, target === el ? "top" : "center"));
    }
  },
  async page(token, a) {
    const pager = document.getElementById("home-pager");
    if (!pointing() || !visible(pager)) {
      goToPage(a.n);
      await sleep(settleMs());
      return;
    }
    // A visible drag: press, swipe 140 px the way the page turns, release.
    const r = pager.getBoundingClientRect();
    const dir = a.n > 0 ? -1 : 1;
    const from = { x: r.left + r.width / 2 - dir * 70, y: r.top + r.height * 0.45 };
    await moveTo(from);
    if (!alive(token)) throw new Stopped();
    press(true);
    try {
      goToPage(a.n);
      const start = performance.now();
      for (;;) {
        const p = Math.min((performance.now() - start) / 320, 1);
        follow({ x: from.x + dir * 140 * p, y: from.y });
        if (p >= 1) break;
        await sleep(16);
        if (!alive(token)) throw new Stopped();
      }
    } finally {
      press(false);
    }
    await sleep(settleMs());
  },
  async quickAdd(token) {
    await ACTIONS.quickAdd(token);
  },
  // A payment through the Add form (setup for a step that starts after one was saved).
  async addPayment(token, a) {
    await goScreen("add", token);
    const input = await need("#amount", token);
    input.value = a.amount;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    (await need(`[data-cat="${a.category}"]`, token)).click();
    const note = await need("#note", token);
    note.value = a.note || "";
    (await need("#save", token)).click();
    await until(() => !state.saving && !state.adding && !state.sheet, token);
  },
  // Apple Wallet on (simulated), then a simulated tap: the payment notification slides in.
  async tap(token) {
    if (!(state.data.connected || {}).apple_pay) await setConnected("apple_pay", true);
    await simulateTap("apple_pay");
    await until(() => (state.data.inbox || []).length > 0, token);
  },
  // The status bar opens the centre on a swipe, not a click: the pointer shows the touch, then the
  // centre opens the same way the swipe does.
  async openCenter(token) {
    const bar = document.getElementById("statusbar");
    if (pointing() && visible(bar)) {
      await moveTo(bar);
      if (!alive(token)) throw new Stopped();
      await clickEffect();
      if (!alive(token)) throw new Stopped();
    }
    openCenter();
    await need("#notify-center .nc-item", token);
  },
  async openPaymentNote(token) {
    await pressEl(await need("#notify-center [data-note-open]", token), token);
    await need("#review-card", token);
  },
  async confirmReview(token) {
    await ACTIONS.confirmReview(token);
  },
  async openCamera(token) {
    await goScreen("home", token);
    if (!isFramed()) return;
    await pressEl(await need('[data-w-tab="photo"]', token), token);
    await pressEl(await need('#home-quick [data-w-screen="camera"]', token), token);
    await need("#cam-screen .lk-samples", token);
  },
  // A sample receipt image through the real OCR, from the camera screen's Samples row.
  async scanInCamera(token, a) {
    if (!isFramed()) return;
    await pressEl(await need(`[data-w-sample="${a.file}"]`, token), token);
    await until(() => document.querySelector("#cam-screen .qa-result, #cam-screen .lk-note.err"), token, 45000);
    await need("#cam-screen [data-w-check]", token);
  },
  async checkInAdd(token) {
    if (!isFramed()) return;
    await pressEl(await need("#cam-screen [data-w-check]", token), token);
    await need("#amount", token);
  },
  async save(token) {
    if (!state.adding) return;
    await pressEl(await need("#save", token), token);
    await until(() => !state.saving && !state.adding && !state.sheet, token);
  },
  async scenario(token, a) {
    if (!(await switchMode("demo", a.name))) throw new Error("scenario");
    assertDemo();
    await sleep(settleMs());
  },
  async notify(token, a) {
    fireNote(a.kind);
  },
  async toggleFactors(token) {
    await pressEl(await need("[data-cooked-toggle]", token), token);
    await sleep(settleMs());
  },
  async click(token, a) {
    await pressEl(await need(a.selector, token), token);
    await sleep(settleMs());
  },
  // A range input moved to `to` over `ms`, firing input events like a finger would.
  async slide(token, a) {
    let el = await need(a.selector, token);
    const from = Number(el.value);
    const step = Number(el.step) || 1;
    const pointer = pointing();
    // Where the thumb is for the current value (the thumb is about 20 px wide).
    const thumb = () => {
      const r = el.getBoundingClientRect();
      const min = Number(el.min) || 0;
      const max = Number(el.max) || 100;
      const f = max > min ? Math.min(Math.max((Number(el.value) - min) / (max - min), 0), 1) : 0;
      return { x: r.left + 10 + f * (r.width - 20), y: r.top + r.height / 2 };
    };
    if (pointer) {
      await ensureVisible(el, token);
      await moveTo(thumb());
      if (!alive(token)) throw new Stopped();
      press(true);
    }
    try {
      const start = performance.now();
      for (;;) {
        if (!alive(token)) throw new Stopped();
        if (!el.isConnected && el.id) el = document.getElementById(el.id) || el; // re-rendered
        const p = Math.min((performance.now() - start) / a.ms, 1);
        const value = Math.round((from + (a.to - from) * p) / step) * step;
        if (Number(el.value) !== value) {
          el.value = String(value);
          el.dispatchEvent(new Event("input", { bubbles: true }));
        }
        if (pointer) follow(thumb());
        if (p >= 1) break;
        await sleep(16);
      }
    } finally {
      if (pointer) press(false);
    }
  },
  async typeAmount(token) {
    await ACTIONS.typeAmount(token);
  },
  async openCover(token) {
    await ACTIONS.openCover(token);
  },
  async pickFlex(token) {
    await ACTIONS.pickFlex(token);
  },
  async confirm(token) {
    await ACTIONS.confirm(token);
  },
  async undo(token) {
    await ACTIONS.undo(token);
  },
};

function runAction(action, token) {
  const fn = TIMELINE_ACTIONS[action.do];
  if (!fn) throw new Error(`unknown action ${action.do}`);
  return fn(token, action);
}

async function resetDemo() {
  if (!state.data || state.data.mode !== "demo") return false;
  const ok = await switchMode("demo");
  return Boolean(ok && state.data && state.data.mode === "demo");
}

// The overlay -------------------------------------------------------------------------------------

function buildOverlay(mode) {
  const root = document.createElement("div");
  root.className = "tour";
  root.id = "tour";
  root.innerHTML = `
    <div class="tour-shield"></div>
    <div class="tour-spot"></div>
    <div class="tour-bubble" role="dialog" aria-modal="true" aria-labelledby="tour-title" aria-describedby="tour-body" tabindex="-1">
      <span class="tour-arrow" aria-hidden="true"></span>
      <div class="tour-head">
        <span class="tour-count" id="tour-count"></span>
        <button class="ghost small tour-skip" id="tour-skip" type="button">Skip tour</button>
      </div>
      <div class="tour-content">
        <h2 id="tour-title"></h2>
        <p id="tour-body"></p>
      </div>
      <div class="tour-progress"${mode === "auto" ? "" : " hidden"}><span id="tour-bar"></span></div>
      <div class="tour-actions">
        <button class="ghost small" id="tour-back" type="button">Back</button>
        <button class="ghost small" id="tour-pause" type="button" aria-pressed="false"${mode === "auto" ? "" : " hidden"}>Pause</button>
        <button class="primary small" id="tour-next" type="button">Next</button>
        <button class="ghost small" id="tour-restart" type="button"${mode === "auto" ? "" : " hidden"}>Restart</button>
      </div>
      <p class="sr-only" id="tour-live" aria-live="polite"></p>
    </div>
    <span class="tour-clock" id="tour-clock" aria-hidden="true"${mode === "auto" && showClock() ? "" : " hidden"}>0:00</span>`;
  if (mode === "auto") root.classList.add("is-timeline");
  if (mode === "auto" && recordMode()) {
    root.classList.add("is-record"); // captions only: no buttons, no counter, no timer
    root.querySelector("#tour-clock").hidden = true;
  }
  document.body.appendChild(root);
  const q = (sel) => root.querySelector(sel);
  return {
    root, spot: q(".tour-spot"), bubble: q(".tour-bubble"), count: q("#tour-count"), title: q("#tour-title"),
    body: q("#tour-body"), content: q(".tour-content"), bar: q("#tour-bar"), back: q("#tour-back"),
    pause: q("#tour-pause"), next: q("#tour-next"), skip: q("#tour-skip"), live: q("#tour-live"),
    restart: q("#tour-restart"), clock: q("#tour-clock"),
  };
}

// The elapsed timer in the corner, for checking timestamps while recording. ?timer=0 hides it.
function showClock() {
  try {
    return new URLSearchParams(window.location.search).get("timer") !== "0";
  } catch (err) {
    return true;
  }
}

// The visible part of an element: clipped to the viewport and to the scrolling screen.
function visibleRect(el) {
  let r = el.getBoundingClientRect();
  let x1 = r.left; let y1 = r.top; let x2 = r.right; let y2 = r.bottom;
  const clip = el.closest("#screen") || el.closest("#phone");
  if (clip && clip !== el) {
    r = clip.getBoundingClientRect();
    x1 = Math.max(x1, r.left); y1 = Math.max(y1, r.top); x2 = Math.min(x2, r.right); y2 = Math.min(y2, r.bottom);
  }
  x1 = Math.max(x1, 0); y1 = Math.max(y1, 0);
  x2 = Math.min(x2, window.innerWidth); y2 = Math.min(y2, window.innerHeight);
  return { x: x1, y: y1, w: Math.max(0, x2 - x1), h: Math.max(0, y2 - y1) };
}

// Auto-play: the caption sits left of the phone when there is room (the app stays fully visible
// for the video), else at the bottom of the screen.
function timelineLayout() {
  const { els } = tour;
  const device = document.getElementById("device");
  const r = isFramed() && device ? device.getBoundingClientRect() : null;
  // Narrow the caption to the room left of the phone (down to 240 px) so it never covers the app.
  els.bubble.style.width = r && r.left - 32 >= 240 ? `${Math.min(320, Math.floor(r.left - 32))}px` : "";
  const size = { w: els.bubble.offsetWidth, h: els.bubble.offsetHeight };
  let x;
  let y;
  if (r && r.left >= size.w + 32) {
    x = r.left - size.w - 24;
    y = Math.max(8, r.top + r.height / 2 - size.h / 2);
  } else {
    x = Math.max(8, (window.innerWidth - size.w) / 2);
    y = Math.max(8, window.innerHeight - size.h - 8);
  }
  els.bubble.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
  els.bubble.dataset.side = "caption";
}

function layout() {
  if (!tour) return;
  if (tour.mode === "auto") {
    timelineLayout();
    return;
  }
  const { els, target, step } = tour;
  const viewport = { w: window.innerWidth, h: window.innerHeight };
  const rect = target && target.isConnected ? visibleRect(target) : null;
  const pad = 6;
  if (rect && rect.w > 0 && rect.h > 0) {
    els.spot.style.transform = `translate(${rect.x - pad}px, ${rect.y - pad}px)`;
    els.spot.style.width = `${rect.w + pad * 2}px`;
    els.spot.style.height = `${rect.h + pad * 2}px`;
  } else {
    els.spot.style.transform = `translate(${viewport.w / 2}px, ${viewport.h / 2}px)`;
    els.spot.style.width = "0px";
    els.spot.style.height = "0px";
  }
  const size = { w: els.bubble.offsetWidth, h: els.bubble.offsetHeight };
  const box = rect && rect.w > 0 ? { x: rect.x - pad, y: rect.y - pad, w: rect.w + pad * 2, h: rect.h + pad * 2 } : null;
  const place = placeBubble(box, size, viewport, step ? step.placement : "center");
  els.bubble.style.transform = `translate(${Math.round(place.x)}px, ${Math.round(place.y)}px)`;
  els.bubble.dataset.side = place.side;
  if (place.arrow != null) els.bubble.style.setProperty("--arrow", `${Math.round(place.arrow)}px`);
}

let layoutQueued = false;
function queueLayout() {
  if (layoutQueued) return;
  layoutQueued = true;
  requestAnimationFrame(() => {
    layoutQueued = false;
    layout();
  });
}

function setBusy(busy) {
  if (!tour) return;
  tour.busy = busy;
  tour.els.next.disabled = busy;
  tour.els.back.disabled = busy || tour.index === 0;
  tour.els.bubble.setAttribute("aria-busy", String(busy));
}

// The step timer (auto-play) and its progress bar, with pause and resume.
function clearTimer() {
  if (!tour) return;
  clearTimeout(tour.timer);
  tour.timer = null;
}

function startTimer(ms) {
  tour.stepMs = ms;
  tour.remaining = ms;
  const bar = tour.els.bar;
  bar.style.transition = "none";
  bar.style.transform = "scaleX(0)";
  void bar.offsetWidth;
  if (!tour.paused) resumeTimer();
}

function resumeTimer() {
  const bar = tour.els.bar;
  tour.startedAt = performance.now();
  bar.style.transition = `transform ${Math.max(tour.remaining, 0)}ms linear`;
  bar.style.transform = "scaleX(1)";
  const token = tour.token;
  tour.timer = setTimeout(() => {
    if (alive(token)) next();
  }, Math.max(tour.remaining, 0));
}

function pauseTimer() {
  if (!tour.timer) return;
  clearTimer();
  tour.remaining -= performance.now() - tour.startedAt;
  const done = 1 - Math.max(tour.remaining, 0) / tour.stepMs;
  tour.els.bar.style.transition = "none";
  tour.els.bar.style.transform = `scaleX(${done})`;
}

function togglePause() {
  if (!tour || tour.mode !== "auto") return;
  if (!tour.paused) tour.pausedAt = elapsed();
  else tour.t0 = performance.now() - tour.pausedAt * 1000;
  tour.paused = !tour.paused;
  tour.els.pause.textContent = tour.paused ? "Resume" : "Pause";
  tour.els.pause.setAttribute("aria-pressed", String(tour.paused));
}

// The timeline player ------------------------------------------------------------------------------

// Seconds since the start of the video, from one clock.
function elapsed() {
  if (!tour) return 0;
  if (tour.paused || tour.seeking) return tour.pausedAt;
  return (performance.now() - tour.t0) / 1000;
}

// What happened when, for checking drift: { step, planned, actual } per step and per action.
export function demoLog() {
  return tour && tour.log ? tour.log.slice() : (lastLog || []).slice();
}
let lastLog = null;

// Late actions of the previous step are kept and run first, so the state each step needs is
// always built; they are logged with their real time.
function enterStep(index) {
  const step = tour.steps[index];
  tour.index = index;
  const late = tour.queue.filter((a) => a.due < step.start);
  tour.queue = [...late, ...step.actions.map((a) => ({ ...a, due: step.start + a.at })).sort((a, b) => a.due - b.due)];
  tour.log.push({ step: step.id, what: "caption", planned: step.start, actual: Number(elapsed().toFixed(3)) });
  presentCaption(step, index);
}

function presentCaption(step, index) {
  const { els, steps } = tour;
  tour.step = step;
  tour.target = null;
  els.count.textContent = `${index + 1} / ${steps.length} · ${clockText(step.start)}`;
  els.title.textContent = step.title;
  els.body.textContent = step.caption;
  els.next.textContent = index === steps.length - 1 ? "Finish" : "Next";
  els.back.disabled = false;
  els.live.textContent = `Step ${index + 1} of ${steps.length}: ${step.title}`;
  els.content.classList.remove("is-new");
  void els.content.offsetWidth;
  if (!prefersReducedMotion()) els.content.classList.add("is-new");
  layout();
}

function startAction(action, token) {
  tour.log.push({ step: tour.steps[tour.index].id, what: action.do, planned: action.due, actual: Number(elapsed().toFixed(3)) });
  tour.running = runAction(action, token)
    .catch((err) => {
      if (err instanceof Stopped || !alive(token)) return;
      tour.log.push({ step: tour.steps[tour.index].id, what: `failed ${action.do}: ${err.message}`, planned: action.due, actual: elapsed() });
      end("error", err.userMessage || "The demo stopped because the app did not answer as expected.");
    })
    .finally(() => {
      if (tour && tour.token === token) tour.running = null;
    });
}

// One clock (elapsed), read by an animation-frame loop (smooth timer and bar) and by a 50 ms
// interval (keeps the steps on time if the browser pauses animation frames). Both run advance();
// neither adds delays, so nothing drifts.
function tick() {
  if (!advance()) return;
  tour.raf = requestAnimationFrame(tick);
}

function advance() {
  if (!tour || tour.mode !== "auto" || tour.ending) return false;
  const t = elapsed();
  const steps = tour.steps;
  const step = steps[tour.index];
  if (tour.els.clock) tour.els.clock.textContent = clockText(t);
  const p = Math.min(Math.max((t - step.start) / (step.end - step.start), 0), 1);
  tour.els.bar.style.transform = `scaleX(${p.toFixed(4)})`;
  if (!tour.paused && !tour.seeking) {
    if (t >= step.end) {
      if (tour.index >= steps.length - 1) {
        if (!tour.running && !tour.queue.length) end("finish");
        return true;
      }
      if (tour.queue.length) tour.log.push({ step: step.id, what: `late ${tour.queue.length}`, planned: step.end, actual: t });
      enterStep(tour.index + 1);
    }
    const due = tour.queue[0];
    if (due && !tour.running && t >= due.due) startAction(tour.queue.shift(), tour.token);
  }
  return true;
}

// Jump to the exact start of a step: reset the demo, rebuild the state it starts from, set the clock.
async function seek(index) {
  if (!tour) return;
  const token = ++tour.token;
  const step = tour.steps[index];
  tour.pausedAt = elapsed();
  tour.seeking = true;
  tour.queue = [];
  setBusy(true);
  try {
    if (tour.running) await Promise.race([tour.running, sleep(5000)]);
    tour.running = null;
    assertDemo();
    resetTaps();
    resetNotifications();
    if (!(await resetDemo())) throw new Error("reset");
    if (state.fundView !== "list") setFundView("list");
    for (const action of step.setup) {
      if (!alive(token)) return;
      await runAction(action, token);
    }
    if (!alive(token)) return;
    tour.seeking = false;
    tour.pausedAt = step.start;
    tour.t0 = performance.now() - step.start * 1000;
    setBusy(false);
    enterStep(index);
    cancelAnimationFrame(tour.raf);
    tour.raf = requestAnimationFrame(tick);
    clearInterval(tour.pulse);
    tour.pulse = setInterval(advance, 50);
  } catch (err) {
    if (err instanceof Stopped || !alive(token)) return;
    end("error", err.userMessage || "The demo stopped because the app did not answer as expected.");
  }
}

// Steps -----------------------------------------------------------------------------------------

async function findTarget(step, token) {
  if (!step.target) return null;
  const selector = (tour.mode === "auto" && step.autoTarget) || step.target;
  try {
    return await need(selector, token, tour.mode === "auto" ? 4000 : 400);
  } catch (err) {
    if (err instanceof Stopped || (tour.mode === "auto" && state.error)) throw err;
    const fallback = step.fallback && document.querySelector(step.fallback);
    return visible(fallback) ? fallback : undefined;
  }
}

function present(step, target, index) {
  const { els, steps, mode } = tour;
  tour.step = step;
  tour.target = target;
  if (target) target.scrollIntoView({ block: "nearest", behavior: prefersReducedMotion() ? "auto" : "smooth" });
  els.count.textContent = `${index + 1} / ${steps.length}`;
  els.title.textContent = step.title;
  els.body.textContent = mode === "auto" && step.autoBody ? step.autoBody : step.body;
  els.next.textContent = index === steps.length - 1 ? "Finish" : "Next";
  els.live.textContent = `Step ${index + 1} of ${steps.length}: ${step.title}`;
  els.content.classList.remove("is-new");
  void els.content.offsetWidth;
  if (!prefersReducedMotion()) els.content.classList.add("is-new");
  layout();
  setTimeout(queueLayout, tokenMs("--dur-slow", 360)); // after a smooth scroll settles
  if (!els.bubble.contains(document.activeElement)) els.next.focus();
}

async function show(index, dir = 1) {
  if (!tour) return;
  const token = ++tour.token;
  clearTimer();
  tour.index = index;
  tour.remaining = null;
  setBusy(true);
  const step = tour.steps[index];
  try {
    if (tour.mode === "auto") {
      assertDemo();
      if (step.autoAction) {
        tour.action = ACTIONS[step.autoAction](token);
        await tour.action;
      } else {
        await goScreen(step.screen, token);
      }
      assertDemo();
    } else {
      await goScreen(step.screen, token);
    }
    if (!alive(token)) return;
    const target = await findTarget(step, token);
    if (!alive(token)) return;
    if (target === undefined) {
      // Nothing to point at: skip the step in the direction of travel.
      const other = index + dir;
      if (other >= 0 && other < tour.steps.length) show(other, dir);
      else end("finish");
      return;
    }
    setBusy(false);
    present(step, target, index);
    if (tour.mode === "auto") startTimer(stepDuration(step));
  } catch (err) {
    if (err instanceof Stopped || !alive(token)) return;
    end("error", err.userMessage || "The demo stopped because the app did not answer as expected.");
  } finally {
    if (tour && tour.token === token) tour.action = null;
  }
}

function next() {
  if (!tour || tour.busy) return;
  if (tour.index >= tour.steps.length - 1) end("finish");
  else if (tour.mode === "auto") seek(tour.index + 1);
  else show(tour.index + 1, 1);
}

// Back: the previous step (auto-play: its exact start, from a fresh demo week and its setup).
function back() {
  if (!tour || tour.busy) return;
  if (tour.mode === "auto") {
    seek(Math.max(tour.index - 1, 0));
    return;
  }
  if (tour.index === 0) return;
  show(tour.index - 1, -1);
}

function restart() {
  if (!tour || tour.busy || tour.mode !== "auto") return;
  seek(0);
}

// Keys: Right / Enter next, Left back, Escape skip, Tab stays in the bubble.
function onKey(event) {
  if (!tour) return;
  const { key } = event;
  if (key === "Escape") {
    event.preventDefault();
    event.stopPropagation();
    end("skip");
  } else if (key === "ArrowRight") {
    event.preventDefault();
    event.stopPropagation();
    next();
  } else if (key === "ArrowLeft") {
    event.preventDefault();
    event.stopPropagation();
    back();
  } else if (key === "Enter") {
    if (event.target.closest && event.target.closest("button")) return; // the button's own click
    event.preventDefault();
    event.stopPropagation();
    next();
  } else if (key === "Tab") {
    trapFocus(event, tour.els.bubble);
  }
}

function onShieldClick(event) {
  event.preventDefault();
  event.stopPropagation();
}

// Start and end -----------------------------------------------------------------------------------

function begin(mode) {
  hideOffer();
  const els = buildOverlay(mode);
  tour = {
    mode, steps: stepsFor(mode), index: 0, token: 0, timer: null, paused: false, busy: false,
    remaining: null, els, target: null, step: null, action: null, ending: false,
    prevFocus: document.activeElement,
    fundView: state.fundView, // auto-play shows the tanks, then gives the person's choice back
    t0: 0, pausedAt: 0, seeking: false, queue: [], running: null, raf: 0, pulse: 0, log: [],
  };
  els.next.addEventListener("click", next);
  els.back.addEventListener("click", back);
  els.skip.addEventListener("click", () => end("skip"));
  els.pause.addEventListener("click", togglePause);
  els.restart.addEventListener("click", restart);
  els.root.querySelector(".tour-shield").addEventListener("click", onShieldClick);
  document.addEventListener("keydown", onKey, true);
  window.addEventListener("resize", queueLayout);
  window.addEventListener("scroll", queueLayout, true);
  if (!prefersReducedMotion()) els.root.classList.add("is-entering");
  els.bubble.focus();
  if (mode === "auto") {
    setAutoNotify(false); // the timeline fires each notification itself, at its time
    if (cursorWanted()) showCursor(document.getElementById("device"));
    seek(0);
  } else {
    show(0, 1);
  }
}

export function tourActive() {
  return Boolean(tour);
}

export function startGuided() {
  if (tour || !state.data) return;
  begin("guided");
}

export async function startAutoplay() {
  if (tour || !state.data) return false;
  if (!canAutoplay(state.data.mode)) {
    state.error = "The demo plays in Demo mode only, so it never touches your data. Choose Demo in Settings first.";
    render();
    return false;
  }
  storageSet("sessionStorage", RUNNING_KEY, "1");
  if (!(await resetDemo())) {
    storageSet("sessionStorage", RUNNING_KEY, null);
    state.error = "The demo could not be reset, so auto-play did not start. Reload the page and try again.";
    render();
    return false;
  }
  begin("auto");
  return true;
}

async function end(reason, message) {
  const t = tour;
  if (!t || t.ending) return;
  t.ending = true;
  t.token += 1;
  clearTimer();
  cancelAnimationFrame(t.raf);
  clearInterval(t.pulse);
  if (t.mode === "auto") lastLog = t.log;
  hideCursor();
  document.removeEventListener("keydown", onKey, true);
  window.removeEventListener("resize", queueLayout);
  window.removeEventListener("scroll", queueLayout, true);
  const { root } = t.els;
  root.classList.add("is-leaving");
  setTimeout(() => root.remove(), prefersReducedMotion() ? 0 : tokenMs("--dur-base", 220));
  if (t.mode === "auto") {
    try {
      await t.action; // let a click in flight finish, so nothing lands after the reset
    } catch (err) {
      // already handled
    }
    const settle = performance.now() + 5000;
    while (state.saving && performance.now() < settle) await sleep(50);
    const live = state.data && state.data.mode !== "demo";
    if (state.fundView !== t.fundView) setFundView(t.fundView);
    resetTaps();
    resetNotifications();
    setAutoNotify(true);
    const reset = live ? false : await resetDemo();
    storageSet("sessionStorage", RUNNING_KEY, null);
    if (message) state.error = reset ? `${message} The demo week has been reset.` : message;
    else if (!reset && !live) state.error = "The demo could not be reset. Choose Demo in Settings, or reload the page.";
    if (message || !reset) render();
  } else {
    if (state.sheet) closeSheet();
    if (state.adding) closeAdd();
    if (state.screen !== "today") document.querySelector('#nav [data-screen="today"]')?.click();
  }
  tour = null;
  if (t.mode === "auto" && recordMode()) showRecordHint(() => startAutoplay()); // another take
  const back = t.prevFocus && t.prevFocus.isConnected && !t.prevFocus.closest("[inert]") ? t.prevFocus : document.getElementById("tour-btn");
  back?.focus();
}

// After a reload in the middle of auto-play: put the demo back to its starting week.
export async function recoverInterruptedAutoplay() {
  if (storageGet("sessionStorage", RUNNING_KEY) !== "1") return;
  storageSet("sessionStorage", RUNNING_KEY, null);
  if (!state.data || state.data.mode !== "demo") return;
  const ok = await resetDemo();
  if (ok) state.flash = "Auto-play was interrupted, so the demo week was reset.";
  else state.error = "Auto-play was interrupted and the demo could not be reset. Choose Demo in Settings.";
  render();
}

// The first-visit welcome, DEMO only. "Skip" hides it for good (Settings can bring it back);
// starting the demo or the tour hides it for this session.
export function maybeOfferTour() {
  const offer = document.getElementById("tour-offer");
  if (!offer || !state.data || state.data.mode !== "demo") return;
  if (storageGet("localStorage", OFFER_KEY) === "off" || storageGet("sessionStorage", OFFER_SEEN_KEY) === "1") return;
  offer.hidden = false;
}

// "Show the welcome tip again" in Settings.
export function resetOffer() {
  storageSet("localStorage", OFFER_KEY, null);
  storageSet("sessionStorage", OFFER_SEEN_KEY, null);
  maybeOfferTour();
}

export function hideOffer(forever = false) {
  const offer = document.getElementById("tour-offer");
  if (offer) offer.hidden = true;
  storageSet("sessionStorage", OFFER_SEEN_KEY, "1");
  if (forever) storageSet("localStorage", OFFER_KEY, "off");
}
