// Entry point: the static shell (header, Add button, toast, bottom navigation) and the first load.

import { closeAdd, closeSheet, loadMap, openAdd, simulateTap, switchMode, undoPayment } from "./actions.js";
import { api } from "./api.js";
import { registerOverlay } from "./closers.js";
import { recordMode, showRecordHint } from "./cursor.js";
import { NATIVE } from "./config.js";
import { applyFrame, initDevice, openApp } from "./device.js";
import { render, renderToast } from "./render.js";
import { trapFocus } from "./sheet.js";
import { hideOffer, maybeOfferTour, recoverInterruptedAutoplay, startAutoplay, startGuided } from "./tour.js";
import { applyState, state } from "./store.js";

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

// A new day in Hong Kong (the status bar clock noticed): fetch the new numbers.
document.addEventListener("ssust:new-day", () => {
  if (state.saving || state.adding || state.sheet) return;
  api("/api/state").then((data) => {
    applyState(data);
    render();
  }).catch(() => {});
});

// First load failed: on the web the local server is not running; in the iOS app the hosted one is
// out of reach.
const WEB_UNREACHABLE = `<div class="card"><div class="explain">The server is not running. Start it with python run.py (or run.bat), then reload this page.</div></div>`;
const NATIVE_UNREACHABLE = `<div class="card"><div class="explain">Could not reach the SSUST server. Check your internet connection, then close and reopen the app.</div></div>`;

api("/api/state").then(async (data) => {
  applyState(data);
  render();
  applyFrame();
  await recoverInterruptedAutoplay();
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
  maybeOfferTour();
}).catch(() => {
  document.getElementById("screen").innerHTML = NATIVE ? NATIVE_UNREACHABLE : WEB_UNREACHABLE;
});
