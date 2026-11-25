// Entry point: the static shell (header, Add button, toast, bottom navigation) and the first load.

import { closeAdd, closeSheet, loadFeedback, loadMap, openAdd, showToast, simulateTap, switchMode, undoPayment } from "./actions.js";
import { api, setReadOnly, wake } from "./api.js";
import { RETRY_MS, WAKE_WAIT_MS } from "./backup.js";
import { registerOverlay } from "./closers.js";
import { recordMode, showRecordHint } from "./cursor.js";
import { NATIVE } from "./config.js";
import { applyFrame, initDevice, openApp } from "./device.js";
import { loadDeviceId } from "./durable.js";
import { render, renderToast } from "./render.js";
import { trapFocus } from "./sheet.js";
import { hideOffer, maybeOfferTour, recoverInterruptedAutoplay, startAutoplay, startGuided } from "./tour.js";
import { applyState, state } from "./store.js";
import { backupIfStale, initBackup, lastSavedState, restoreIfNeeded, scheduleBackup } from "./sync.js";

// The iPhone app: start waking the hosted server (it sleeps when idle) before anything else.
wake();

// The iPhone app: no phone frame, no demo or tour, room for the status bar, no double-tap zoom.
// The web page keeps its own viewport (index.html), so people can still zoom there.
if (NATIVE) {
  document.documentElement.classList.add("native");
  document.querySelector('meta[name="viewport"]')?.setAttribute("content",
    "width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover");
}

document.getElementById("nav").addEventListener("click", (event) => {
  const btn = event.target.closest("button");
  if (!btn || !btn.dataset.screen) return;
  state.error = "";
  state.flash = "";
  state.undoId = null;
  state.errorField = null;
  state.fundDraft = null;
  state.sheet = null;
  state.adding = false;
  state.past = null; // the Week tab always opens on the current week
  if (btn.dataset.screen === "map") loadMap();
  else {
    state.screen = btn.dataset.screen;
    state.mapLoading = false;
    if (state.screen === "feedback") {
      state.feedback.sent = false;
      state.feedback.list = null;
      loadFeedback();
    }
    render();
  }
});

// The Add payment button sits above the navigation, outside the re-rendered screen.
document.getElementById("add").addEventListener("click", openAdd);

// The LIVE / DEMO switch is in Settings; the header always shows the current mode.
document.addEventListener("click", (event) => {
  const btn = event.target.closest("button[data-switch]");
  if (!btn || !state.data || btn.dataset.switch === state.data.mode) return;
  hideOffer();
  switchMode(btn.dataset.switch);
});

// The toast after a save: Undo asks once more ("Yes, undo" / "Keep"), like the payment rows.
document.getElementById("toast").addEventListener("click", (event) => {
  const toast = state.toast;
  if (!toast) return;
  if (event.target.closest("[data-toast-undo]")) {
    toast.confirming = true;
    renderToast();
    document.querySelector("[data-toast-yes]")?.focus();
  } else if (event.target.closest("[data-toast-no]")) {
    toast.confirming = false;
    renderToast();
    document.querySelector("[data-toast-undo]")?.focus();
  } else if (event.target.closest("[data-toast-yes]")) {
    undoPayment(toast.undoId);
  }
});

// The guided tour and the auto-play demo: the header help button, and every data-tour button
// (Settings, the first-visit welcome). Auto-play itself refuses to start in LIVE.
document.getElementById("tour-btn").addEventListener("click", startGuided);
document.addEventListener("click", (event) => {
  const tourBtn = event.target.closest("[data-tour]");
  if (tourBtn && !tourBtn.disabled) {
    hideOffer();
    if (tourBtn.dataset.tour === "auto") startAutoplay();
    else startGuided();
    return;
  }
  const offerBtn = event.target.closest("[data-offer]");
  if (offerBtn) hideOffer(offerBtn.dataset.offer === "never");
});

// The Add sheet and the reallocation modal: Escape steps back (modal -> form -> closed),
// Tab stays inside.
document.getElementById("sheet").addEventListener("keydown", (event) => {
  if (!state.sheet && !state.adding) return;
  if (event.key === "Escape") {
    event.preventDefault();
    if (state.sheet) closeSheet();
    else closeAdd();
  } else if (event.key === "Tab") {
    trapFocus(event, event.currentTarget);
  }
});

initDevice();

// The Add sheet and its reallocation step, for the shared close controls (closers.js).
registerOverlay({ name: "add", layer: 10, isOpen: () => state.adding && !state.sheet, close: closeAdd });
registerOverlay({ name: "sheet", layer: 11, isOpen: () => Boolean(state.sheet), close: closeSheet });

// "Simulate a tap" (Settings, Demo & help, and the demo controls beside the phone). It works from
// anywhere, also on the home screen, like a real payment would.
document.addEventListener("click", (event) => {
  const tap = event.target.closest("[data-tap]");
  if (tap) {
    simulateTap(tap.dataset.tap);
    return;
  }
});

// The state from the server. In the iPhone app, when the server has lost this phone's data (a
// wiped free host), it is first rebuilt from the copy on the phone (sync.js); the web gets it as is.
async function loadState() {
  const data = await api("/api/state");
  const restored = await restoreIfNeeded(data);
  return restored ? { data: restored.state, banner: restored.banner } : { data, banner: "" };
}

function showBanner(banner) {
  if (!banner) return;
  showToast({ text: banner });
  renderToast();
}

// A restore that happened in the background (a backup showed the server had lost rows).
function onRestored({ state: data, banner }) {
  if (!data) return;
  if (state.past) state.data = data;
  else applyState(data);
  render();
  showBanner(banner);
}

// iPhone app, server out of reach or still waking up: the last saved numbers, read-only, with
// "Offline, last updated hh:mm" (render.js) instead of a spinner or an empty app.
let retryTimer = null;

function showOffline(saved) {
  state.offline = { since: saved.savedAt };
  setReadOnly(true);
  if (saved.data) applyState(saved.data);
  render();
}

function showOnline({ data, banner }) {
  const wasOffline = Boolean(state.offline);
  state.offline = null;
  setReadOnly(false);
  clearTimeout(retryTimer);
  if (state.past && !wasOffline) state.data = data;
  else applyState(data);
  render();
  showBanner(banner);
}

function retryLater() {
  clearTimeout(retryTimer);
  retryTimer = setTimeout(reconnect, RETRY_MS);
}

function reconnect() {
  loadState().then((answer) => {
    showOnline(answer);
    scheduleBackup();
  }).catch(retryLater);
}

// A new day in Hong Kong (the status bar clock noticed): fetch the new numbers.
document.addEventListener("ssust:new-day", () => {
  if (state.offline || state.saving || state.adding || state.sheet) return;
  loadState().then(({ data, banner }) => {
    applyState(data);
    render();
    showBanner(banner);
  }).catch(() => {});
});

// Back to the app (or the tab): fetch the numbers again, so a payment sent by a Shortcut or a
// new day shows without a restart. The iPhone app also refreshes an old copy of its data.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible") return;
  if (state.offline) {
    reconnect();
    return;
  }
  if (!state.data || state.saving || state.adding || state.sheet) return;
  loadState().then(({ data, banner }) => {
    if (state.past) state.data = data;
    else applyState(data);
    render();
    showBanner(banner);
    backupIfStale();
  }).catch(() => {
    // iPhone app: the server is out of reach again, keep what is on screen read-only.
    if (!NATIVE || !state.data) return;
    showOffline({ savedAt: (state.updatedAt || new Date()).toISOString(), data: null });
    retryLater();
  });
});

// First load failed: on the web the local server is not running; in the iOS app the hosted one is
// out of reach.
const WEB_UNREACHABLE = `<div class="card"><div class="explain">The server is not running. Start it with python run.py (or run.bat), then reload this page.</div></div>`;
const NATIVE_UNREACHABLE = `<div class="card"><div class="explain">Could not reach the SSUST server. Check your internet connection, then close and reopen the app.</div></div>`;

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// iPhone app launch: this phone's id and copy from durable storage, then the server's state. If the
// server has not answered within WAKE_WAIT_MS, the saved numbers show meanwhile (read-only).
async function launchNative() {
  await loadDeviceId();
  await initBackup(() => (state.offline ? null : state.data), onRestored);
  const saved = await lastSavedState();
  const first = loadState();
  if (saved) {
    const late = await Promise.race([first.then(() => false, () => false), wait(WAKE_WAIT_MS).then(() => true)]);
    if (late) {
      showOffline(saved);
      applyFrame();
    }
  }
  let answer;
  try {
    answer = await first;
  } catch (err) {
    if (saved) {
      if (!state.offline) {
        showOffline(saved);
        applyFrame();
      }
      retryLater();
    } else {
      document.getElementById("screen").innerHTML = NATIVE_UNREACHABLE;
    }
    return;
  }
  showOnline(answer);
  applyFrame();
  scheduleBackup(); // a fresh copy at every app open
}

if (NATIVE) launchNative();
else api("/api/state").then(async (data) => {
  applyState(data);
  render();
  applyFrame();
  if (!NATIVE) await recoverInterruptedAutoplay();
  if (recordMode()) {
    // ?record=1: a clean screen for the video. Space starts the demo, Esc stops it.
    document.body.classList.add("record-mode");
    hideOffer();
    const take = () => showRecordHint(async () => {
      if (!(await startAutoplay())) take();
    });
    take();
    return;
  }
  if (!NATIVE) maybeOfferTour();
}).catch(() => {
  document.getElementById("screen").innerHTML = NATIVE ? NATIVE_UNREACHABLE : WEB_UNREACHABLE;
});
