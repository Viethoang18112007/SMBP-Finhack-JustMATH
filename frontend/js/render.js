// Draws the current screen, the Add sheet and the toast, then wires the buttons.

import { applyNumbers, chooseCampus, commit, confirmInbox, dismissInbox, loadMap, onSave, scanReceipt, setConnected, showToast, showWeek, simulateTap, switchMode, undoPayment } from "./actions.js";
import { renderDeskSide, updateReviewPreview } from "./inbox.js";
import { bindBudget } from "./budget.js";
import { applyFrame, renderHome } from "./device.js";
import { escapeHtml, hk, longDate, parseAmount } from "./format.js";
import { previewLine } from "./preview.js";
import { animateBars, animateCounts, animateEntrances, animateTanks, cancelSheetClose, captureTanks, moveNavPill, closeSheetAnimated, enterScreen, isSheetClosing, openSheetAnimated, screenEnterClass } from "./motion.js";
import { clearMap, mountMap, selectPlace } from "./mapview.js";
import { selectOption, sheetHtml } from "./sheet.js";
import { setFundView, setPhoneView, state } from "./store.js";
import { resetOffer } from "./tour.js";
import { addSheetHtml } from "./screens/add.js";
import { dayScreen } from "./screens/day.js";
import { mapScreen } from "./screens/map.js";
import { settingsScreen } from "./screens/settings.js";
import { todayScreen } from "./screens/today.js";
import { weekScreen } from "./screens/week.js";

const screens = { today: todayScreen, week: weekScreen, day: dayScreen, settings: settingsScreen, map: mapScreen };
// Screens where the Add payment button sits above the navigation.
const WITH_ADD = new Set(["today", "week", "day", "map"]);

function go(screen) {
  state.screen = screen;
  render();
}

// The header: the mode must be obvious on every screen and in any screenshot.
function renderMode() {
  const mode = state.data ? state.data.mode : null;
  const phone = document.getElementById("phone");
  phone.classList.toggle("is-demo", mode === "demo");
  phone.classList.toggle("is-live", mode === "live");
  const badge = document.getElementById("mode-badge");
  if (mode === "demo") {
    badge.textContent = "Demo";
    badge.title = `Demo mode: sample data, fixed date ${longDate(state.data.today)}`;
  } else if (mode === "live") {
    badge.textContent = "Live";
    badge.title = "Live mode: your own data";
  }
}

// The toast above the Add button: a one-time message, with Undo after a save.
export function renderToast() {
  const el = document.getElementById("toast");
  if (state.flash) {
    showToast({ text: state.flash });
    state.flash = "";
  }
  const t = state.toast;
  if (!t) {
    el.hidden = true;
    el.innerHTML = "";
    document.getElementById("phone").classList.remove("has-toast");
    return;
  }
  let actions = "";
  if (t.undoId != null && t.confirming) {
    actions = `<span class="toast-ask">Undo it?</span><button class="toast-btn" type="button" data-toast-yes>Yes, undo</button><button class="toast-btn" type="button" data-toast-no>Keep</button>`;
  } else if (t.undoId != null) {
    actions = `<button class="toast-btn" type="button" data-toast-undo>Undo</button>`;
  }
  el.innerHTML = `<span class="toast-text">${escapeHtml(t.text)}</span>${actions}`;
  el.hidden = false;
  document.getElementById("phone").classList.add("has-toast");
  el.querySelectorAll("button").forEach((btn) => { btn.disabled = state.saving; });
}

// The view a list belongs to: the screen, plus the map's campus and filters (a new filter
// shows a new list, which fades in instead of snapping).
function viewKey() {
  if (state.screen !== "map") return `${state.data.mode}:${state.screen}`;
  return `${state.data.mode}:map:${state.data.campus}:${state.mapKind}:${state.mapRadius}:${state.mapFitsOnly}`;
}

// What the last render showed, to animate only real changes (never the first paint).
let lastScreen = null;
let lastMode = null;

export function render() {
  clearMap();
  renderMode();
  const root = document.getElementById("screen");
  const nav = document.getElementById("nav");
  if (!state.view) {
    root.innerHTML = `<div class="card"><div class="explain">Waiting for the SSUST server.</div></div>`;
    return;
  }
  const mode = state.data.mode;
  const enter = lastMode && lastMode !== mode ? "enter-up" : screenEnterClass(lastScreen, state.screen);
  lastScreen = state.screen;
  lastMode = mode;
  captureTanks(root); // the levels on screen now, so a new render continues from them
  root.innerHTML = screens[state.screen](state.view);
  root.classList.toggle("is-map", state.screen === "map");
  enterScreen(root, enter);
  animateEntrances(root, viewKey(), Boolean(enter));
  nav.querySelectorAll("button").forEach((btn) => {
    const on = btn.dataset.screen === state.screen || (btn.dataset.screen === "week" && state.screen === "day");
    btn.classList.toggle("on", on);
    if (on) btn.setAttribute("aria-current", "page");
    else btn.removeAttribute("aria-current");
  });
  moveNavPill(nav);
  document.getElementById("dock").hidden = !(state.view.ready && WITH_ADD.has(state.screen));
  renderToast();
  // The sheet: the reallocation step when a payment needs it, else the Add form.
  const sheet = document.getElementById("sheet");
  const content = state.sheet ? sheetHtml(state.sheet) : state.adding ? addSheetHtml() : "";
  if (content) {
    const wasOpen = !sheet.hidden && !isSheetClosing(sheet);
    cancelSheetClose(sheet);
    sheet.innerHTML = content;
    sheet.hidden = false;
    sheet.dataset.backdrop = state.sheet ? "sheet" : "add"; // a tap on the dimmed backdrop closes it
    if (!wasOpen) openSheetAnimated(sheet);
  } else if (!sheet.hidden && !isSheetClosing(sheet)) {
    closeSheetAnimated(sheet);
  }
  // While a payment is being saved, no second click can send it again.
  sheet.querySelectorAll("button, input").forEach((btn) => { btn.disabled = state.saving; });
  // The sheet owns the focus: everything behind it is inert while it is open.
  const open = Boolean(content);
  root.inert = open;
  nav.inert = open;
  document.getElementById("bottom").inert = open;
  document.querySelector(".top").inert = open;
  document.getElementById("tour-offer").inert = open;
  // CSSOM writes are allowed by the CSP; inline style attributes in markup are not.
  animateBars(root);
  animateCounts(root, hk);
  animateTanks(root, state.tankFlow);
  state.tankFlow = null; // shown once, right after the payment
  renderHome();
  renderDeskSide();
  bind();
}

// Picking a fund updates the chips and the preview in place, so focus stays on the chip.
function pickCategory(btn) {
  state.draft.category = btn.dataset.cat;
  document.querySelectorAll("[data-cat]").forEach((el) => {
    const on = el === btn;
    el.classList.toggle("on", on);
    el.setAttribute("aria-pressed", String(on));
  });
  updatePreview();
}

// The amount field, the slider and the quick chips stay in step; the preview follows all three.
function syncSlider() {
  const input = document.getElementById("amount");
  const slider = document.getElementById("amount-slider");
  if (!input || !slider) return;
  const cents = parseAmount(input.value) || 0;
  const dollars = Math.floor(cents / 100);
  slider.value = String(Math.min(dollars, Number(slider.max)));
  slider.setAttribute("aria-valuetext", hk(cents));
}

function setAmount(dollars) {
  const input = document.getElementById("amount");
  if (!input) return;
  input.value = dollars > 0 ? String(dollars) : "";
  updatePreview();
  syncSlider();
}

function updatePreview() {
  const input = document.getElementById("amount");
  const preview = document.getElementById("preview");
  if (!input || !preview) return;
  state.draft.amount = input.value;
  if (state.error) {
    // Typing again clears the old message; Save checks the amount again.
    state.error = "";
    document.getElementById("amount-error").textContent = "";
    input.removeAttribute("aria-invalid");
    input.closest(".amount-field")?.classList.remove("invalid");
  }
  preview.textContent = previewLine(state.view, parseAmount(input.value), state.draft.category);
}

function bind() {
  document.getElementById("back-week")?.addEventListener("click", () => go("week"));
  document.querySelectorAll("[data-screen-go]").forEach((btn) => btn.addEventListener("click", () => go(btn.dataset.screenGo)));
  document.querySelectorAll("[data-cat]").forEach((btn) => btn.addEventListener("click", () => pickCategory(btn)));
  document.getElementById("save")?.addEventListener("click", onSave);
  // Enter in the amount or note field saves, like a form.
  ["amount", "note"].forEach((id) => document.getElementById(id)?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      onSave();
    }
  }));
  document.querySelector("[data-phone-view]")?.addEventListener("click", () => {
    setPhoneView(!state.phoneView);
    if (state.phoneView) state.deviceView = "app";
    applyFrame();
    render();
    document.querySelector("[data-phone-view]")?.focus();
  });
  document.querySelector("[data-cooked-toggle]")?.addEventListener("click", () => {
    state.cookedOpen = !state.cookedOpen;
    render();
    document.querySelector("[data-cooked-toggle]")?.focus();
  });
  document.querySelectorAll("[data-fund-view]").forEach((btn) => btn.addEventListener("click", () => {
    if (state.fundView === btn.dataset.fundView) return;
    setFundView(btn.dataset.fundView);
    render();
    document.querySelector(`[data-fund-view="${state.fundView}"]`)?.focus();
  }));
  // The consequence preview follows the amount as it is typed, without re-rendering the form.
  document.getElementById("amount")?.addEventListener("input", () => {
    updatePreview();
    syncSlider();
  });
  document.querySelectorAll("[data-connect]").forEach((btn) => btn.addEventListener("click", () => {
    setConnected(btn.dataset.connect, btn.getAttribute("aria-pressed") !== "true");
  }));
  document.querySelectorAll("[data-review-fund]").forEach((sel) => sel.addEventListener("change", () => updateReviewPreview(sel)));
  document.querySelectorAll("[data-review-confirm]").forEach((btn) => btn.addEventListener("click", () => {
    const id = Number(btn.dataset.reviewConfirm);
    confirmInbox(id, document.getElementById(`review-fund-${id}`).value);
  }));
  document.querySelectorAll("[data-review-dismiss]").forEach((btn) => btn.addEventListener("click", () => dismissInbox(Number(btn.dataset.reviewDismiss))));
  document.getElementById("scan-btn")?.addEventListener("click", () => document.getElementById("scan-file")?.click());
  document.getElementById("scan-file")?.addEventListener("change", (event) => scanReceipt(event.target.files && event.target.files[0]));
  document.getElementById("amount-slider")?.addEventListener("input", (event) => setAmount(Number(event.target.value)));
  document.querySelectorAll("[data-quick]").forEach((btn) => btn.addEventListener("click", () => setAmount(Number(btn.dataset.quick))));
  bindBudget();
  document.querySelectorAll("[data-undo]").forEach((btn) => btn.addEventListener("click", () => {
    state.undoId = Number(btn.dataset.undo);
    render();
    document.querySelector("[data-undo-yes]")?.focus();
  }));
  document.querySelectorAll("[data-undo-yes]").forEach((btn) => btn.addEventListener("click", () => undoPayment(btn.dataset.undoYes)));
  document.querySelectorAll("[data-undo-no]").forEach((btn) => btn.addEventListener("click", () => {
    const id = state.undoId;
    state.undoId = null;
    render();
    document.querySelector(`[data-undo="${id}"]`)?.focus();
  }));
  document.querySelectorAll("[data-day]").forEach((btn) => btn.addEventListener("click", () => {
    state.day = btn.dataset.day;
    go("day");
  }));
  document.querySelectorAll("[data-scenario]").forEach((btn) => btn.addEventListener("click", () => switchMode("demo", btn.dataset.scenario)));
  document.querySelectorAll("[data-week]").forEach((btn) => btn.addEventListener("click", () => showWeek(btn.dataset.week)));
  document.getElementById("apply")?.addEventListener("click", applyNumbers);
  document.getElementById("reset-tips")?.addEventListener("click", () => {
    resetOffer();
    showToast({ text: "The welcome tip is back at the top." });
    renderToast();
  });
  document.querySelectorAll("[data-kind]").forEach((btn) => btn.addEventListener("click", () => {
    state.mapKind = btn.dataset.kind;
    loadMap();
  }));
  document.getElementById("radius")?.addEventListener("change", (event) => {
    state.mapRadius = event.target.value;
    loadMap();
  });
  document.getElementById("campus")?.addEventListener("change", (event) => chooseCampus(event.target.value));
  document.getElementById("fits-only")?.addEventListener("click", () => {
    state.mapFitsOnly = !state.mapFitsOnly;
    state.selectedId = "";
    render();
    document.getElementById("fits-only")?.focus();
  });
  document.querySelectorAll("[data-place]").forEach((btn) => btn.addEventListener("click", () => {
    selectPlace(btn.dataset.place);
  }));
  const sheetEl = document.getElementById("sheet");
  sheetEl.querySelectorAll('input[name="cover"]').forEach((input) => input.addEventListener("change", () => {
    selectOption(sheetEl, state.sheet, input.value);
  }));
  document.getElementById("confirm-cover")?.addEventListener("click", () => commit(state.sheet, state.sheet && state.sheet.selected));
  if (state.sheet && !sheetEl.contains(document.activeElement)) {
    (sheetEl.querySelector('input[name="cover"]:checked') || sheetEl.querySelector("button"))?.focus();
  } else if (state.adding && !state.saving && !sheetEl.contains(document.activeElement)) {
    document.getElementById("amount")?.focus();
  }
  mountMap();
}
