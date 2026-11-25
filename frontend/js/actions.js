// User actions that call the server, then re-render.

import { api } from "./api.js";
import { FUND_FIELDS, FUND_NAME, hk, newRequestId, parseAmount, plainAmount } from "./format.js";
import { render, renderToast } from "./render.js";
import { leaveElement } from "./motion.js";
import { readTotal } from "./ocr.js";
import { nativeScanner, readNative } from "./scanner.js";
import { scanFailure } from "./scanerror.js";
import { nextTap, reviewDraft, showNotification } from "./inbox.js";
import { defaultChoice } from "./sheet.js";
import { applyState, state } from "./store.js";
import { confirmBody, reviewAmountError, typoAnswered } from "./tap.js";
import { budgetMismatch } from "./budget.js";

// What the tanks animate after a save: which fund paid, and which others gave to it.
function flowOf(payment) {
  return payment ? { category: payment.category, from: payment.from || {} } : null;
}

// Server messages are for developers; the student sees plain words next to the field.
const PAYMENT_WORDS = {
  "Enter an amount greater than zero.": "Enter an amount above HK$0, like 48 or 12.50.",
  "The five funds cannot cover this.": "Your funds can't cover this amount. Try a smaller amount.",
  "Set the five funds first.": "Set your weekly budget first, in Settings.",
};

export function paymentError(err) {
  if (!err.fromServer) return err.message; // network: already plain words
  return PAYMENT_WORDS[err.message] || "This payment could not be saved. Check the amount and try again.";
}

function fundError(err) {
  if (err.field && err.minimum != null) {
    return `Already spent ${hk(err.minimum)} this week. Enter ${hk(err.minimum)} or more.`;
  }
  if (err.field) return "Enter an amount of 0 or more, like 120 or 45.50.";
  return err.message;
}

// The toast above the Add button. It hides by itself unless the person is using it.
let toastTimer = null;

export function showToast(toast, ms = 6000) {
  state.toast = toast;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    const el = document.getElementById("toast");
    if (state.toast !== toast || toast.confirming || (el && el.contains(document.activeElement))) return;
    state.toast = null;
    renderToast();
  }, ms);
}

export function openAdd() {
  state.draft = { amount: "", category: "main", note: "" };
  state.scan = null;
  state.attempt = null;
  state.error = "";
  state.adding = true;
  state.sheet = null;
  state.undoId = null;
  render();
  document.getElementById("amount")?.focus();
}

// Close the Add sheet without saving; focus goes back to the Add button.
export function closeAdd() {
  if (state.saving) return;
  state.adding = false;
  state.sheet = null;
  state.error = "";
  state.scan = null;
  render();
  document.getElementById("add")?.focus();
}

// What is typed in the Add form now, so a re-render keeps it.
function keepDraft() {
  const amount = document.getElementById("amount");
  const note = document.getElementById("note");
  if (amount) state.draft.amount = amount.value;
  if (note) state.draft.note = note.value;
}

// Scan receipt: read the receipt, ask the server for the total, pre-fill the form.
// Never saves: the student checks the amount, picks the fund and taps Save as usual.
// In the iPhone app (scanner.js) the phone reads it: the document camera when `file` is null, else
// the picked photo; only the text goes to the server. Elsewhere, or if the phone cannot read a
// picked photo, the offline tesseract.js reader (ocr.js) reads the file.
export async function scanReceipt(file) {
  const scanner = nativeScanner();
  if ((!file && !scanner) || !state.adding || (state.scan && state.scan.status === "reading")) return;
  keepDraft();
  state.scan = { status: "reading", percent: 0, words: scanner ? "Reading on the phone" : "Loading the offline reader" };
  render();
  let result = null;
  let read = "";
  let phone = false; // the phone read the text: it stays visible under the scan row ("What the phone read")
  const stageError = (message) => Object.assign(new Error(message), { scanStage: true });
  try {
    let scan = null;
    if (scanner) {
      let text = null;
      try {
        text = await readNative(scanner, file);
      } catch (err) {
        if (!state.adding) return;
        if (err && (err.code === "cancelled" || err.code === "camera_denied")) {
          keepDraft();
          state.scan = err.code === "cancelled" ? null : { status: "camera_off" };
          render();
          return;
        }
        if (err && (err.code === "no_pages" || err.code === "no_text")) throw stageError(scanFailure(err.code, err));
        if (!file) throw stageError(scanFailure("plugin", err)); // no picture for the offline reader to fall back on
      }
      if (text !== null) {
        phone = true;
        read = text;
        try {
          scan = { text, result: await api("/api/receipt/parse", { text }) };
        } catch (err) {
          throw stageError(scanFailure("server", err));
        }
      }
    }
    if (!scan) {
      scan = await readTotal(file, (text) => api("/api/receipt/parse", { text }), (percent, words) => {
        if (!state.scan || state.scan.status !== "reading") return;
        state.scan.percent = percent;
        state.scan.words = words;
        const el = document.getElementById("scan-status");
        if (el) el.textContent = percent ? `${words}: ${percent}%` : `${words}…`;
      });
    }
    read = scan.text;
    result = scan.result;
  } catch (err) {
    if (!state.adding) return;
    keepDraft();
    state.scan = { status: "error", message: err && err.scanStage ? err.message : "", text: phone ? read.slice(0, 800) : null, phone };
    render();
    return;
  }
  if (!state.adding) return;
  keepDraft();
  if (result.found) {
    state.draft.amount = plainAmount(result.amount);
    if (result.merchant) state.draft.note = result.merchant.slice(0, 40);
    const entry = result.entry;
    if (entry) state.draft.category = entry.category;
    state.error = "";
    state.scan = { status: "found", guess: Boolean(result.guess), line: result.line, merchant: result.merchant, reason: entry ? entry.reason : "",
      typo: entry && entry.typo ? entry.typo.reason : "", text: read.slice(0, 800), phone };
  } else {
    // What the reader saw, so a failed photo can be checked (and sent to us) instead of guessed at.
    state.scan = { status: "none", text: read.slice(0, 800), reason: result.reason || "" };
    state.scan.phone = phone;
  }
  render();
}

let mapToken = 0;
let weekToken = 0;

// Live and demo never share UI state: anything read in one mode is dropped on a switch.
function forgetModeData() {
  mapToken += 1;
  weekToken += 1;
  Object.assign(state, {
    past: null,
    map: null,
    mapLoading: false,
    selectedId: "",
    day: null,
    draft: { amount: "", category: "main", note: "" },
    sheet: null,
    adding: false,
    toast: null,
    showNotice: false,
    error: "",
    undoId: null,
    flash: "",
    errorField: null,
    fundDraft: null,
    review: {},
    screen: "today",
  });
}

// mode "live", or "demo" with an optional demo week ("sample", "empty", "over").
// Switching to demo always restarts that demo week. Returns true when the server agreed.
export async function switchMode(mode, scenario) {
  const body = mode === "demo" && scenario ? { mode: "demo", scenario } : { mode };
  try {
    const data = await api("/api/mode", body);
    forgetModeData();
    applyState(data);
    render();
    return true;
  } catch (err) {
    state.error = err.message;
    render();
    return false;
  }
}

// Show a week on the Week screen. Past weeks are read-only; the server refuses future ones.
export async function showWeek(week) {
  const token = ++weekToken;
  if (!week || week === state.data.weekStart) {
    state.past = null;
    state.screen = "week";
    render();
    return;
  }
  try {
    const data = await api(`/api/state?week=${encodeURIComponent(week)}`);
    if (token !== weekToken || data.mode !== state.data.mode) return;
    state.past = data;
    state.error = "";
  } catch (err) {
    if (token !== weekToken) return;
    state.error = err.message;
  }
  state.screen = "week";
  render();
}

// The request id for this amount and category: the same one again after a failed or repeated
// submit (the server then saves at most one payment), a new one when the payment changes.
function requestIdFor(cents, category) {
  const key = `${cents}|${category}`;
  if (!state.attempt || state.attempt.key !== key) state.attempt = { key, requestId: newRequestId() };
  return state.attempt.requestId;
}

// After a save: back to Today, numbers count to their new values, a toast offers Undo.
function saved(data, extra) {
  const p = data.payment;
  const left = data.state.view.todayRemaining;
  applyState(data.state, {
    ...extra,
    sheet: null,
    adding: false,
    screen: "today",
    past: null,
    error: "",
    attempt: null,
    undoId: null,
  });
  if (p) {
    const today = left != null ? ` · ${hk(Math.max(left, 0))} left today` : "";
    showToast({ text: `Saved ${hk(p.amount)} · ${FUND_NAME[p.category]}${today}`, undoId: p.id, confirming: false });
  }
  render();
  document.getElementById("add")?.focus();
}

// A payment saved without a reallocation step (Add payment, or Confirm on the review card).
function savedDirect(data) {
  saved(data, { showNotice: data.level === 1, tankFlow: flowOf(data.payment) });
}

// Map: "Log a meal here" opens Add payment for that place (Main meals, its name as the note).
// Saved as a normal payment; the place goes with it for the campus medal.
export function logMealAt(placeId) {
  const place = state.map && state.map.places.find((p) => p.id === placeId);
  if (!place) return;
  state.draft = { amount: "", category: "main", note: place.name.slice(0, 40), place: { id: place.id, name: place.name.slice(0, 40) } };
  state.scan = null;
  state.attempt = null;
  state.error = "";
  state.sheet = null;
  state.undoId = null;
  state.adding = true;
  render();
  document.getElementById("amount")?.focus();
}

export async function onSave() {
  if (state.saving) return;
  const raw = document.getElementById("amount").value;
  const note = document.getElementById("note").value.trim();
  const category = state.draft.category;
  const place = state.draft.place || null;
  state.draft = { amount: raw, category, note, place };
  const cents = parseAmount(raw);
  if (cents == null) {
    state.error = "Enter an amount above HK$0, like 48 or 12.50.";
    render();
    document.getElementById("amount")?.focus();
    return;
  }
  const requestId = requestIdFor(cents, category);
  state.saving = true;
  state.error = "";
  render();
  try {
    const body = { amount: raw, category, note, requestId };
    if (place) body.place = place; // a meal logged from the map (campus medal)
    const data = await api("/api/payments", body);
    state.saving = false;
    if (data.needsConfirm) {
      state.sheet = {
        level: data.level,
        options: data.options,
        selected: defaultChoice(data.options),
        amount: cents,
        fundsNow: data.state.view.fundsNow,
        tomorrow: data.state.view.tomorrow,
        todayRemaining: data.state.view.todayRemaining,
        category,
        amountRaw: raw,
        note,
        requestId,
        place,
      };
      state.data = data.state;
      state.view = data.state.view;
      render();
      return;
    }
    savedDirect(data);
  } catch (err) {
    state.saving = false;
    state.error = paymentError(err);
    render();
    document.getElementById("amount")?.focus();
  }
}

// Undo one of this week's payments. The server recomputes every balance without it.
export async function undoPayment(id) {
  if (state.saving) return;
  state.saving = true;
  try {
    const data = await api("/api/payments/undo", { id: Number(id) });
    await leaveElement(document.querySelector(`[data-key="p-${Number(id)}"]`));
    applyState(data.state, { undoId: null, error: "", showNotice: false });
    showToast({ text: "Payment undone. Everything is back as it was." });
  } catch (err) {
    state.undoId = null;
    state.toast = null;
    state.error = err.fromServer ? "This payment could not be undone. It may already be undone." : err.message;
  }
  state.saving = false;
  render();
}

// Leave the reallocation step without saving: back to the Add form, focus on Save.
export function closeSheet() {
  if (state.saving) return;
  state.sheet = null;
  render();
  document.getElementById("save")?.focus();
}

export async function commit(pending, choice) {
  if (state.saving || !pending || !choice) return;
  state.saving = true;
  render();
  try {
    const data = pending.inboxId
      ? await api("/api/inbox/confirm", confirmBody(pending.inboxItem, pending.category, pending.amountRaw, true, choice))
      : await api("/api/payments", {
        amount: pending.amountRaw,
        category: pending.category,
        note: pending.note,
        choice,
        requestId: pending.requestId,
        place: pending.place || null,
      });
    state.saving = false;
    saved(data, { showNotice: false, tankFlow: flowOf(data.payment) });
  } catch (err) {
    state.saving = false;
    state.sheet = null;
    state.error = paymentError(err);
    state.adding = true;
    render();
  }
}

// Connected payments (simulated). A tap adds a sample payment to the server inbox and shows the
// notification; Confirm runs the same payment logic as Add payment, overspend step included.
export async function setConnected(source, on) {
  try {
    applyState(await api("/api/connected", { source, on }));
  } catch (err) {
    state.error = err.message;
  }
  render();
  document.querySelector(`[data-connect="${source}"]`)?.focus();
}

export async function simulateTap(source) {
  const tap = nextTap(source);
  try {
    const data = await api("/api/inbox", tap);
    applyState(data.state);
    render();
    showNotification(data.item);
  } catch (err) {
    state.error = err.message;
    render();
  }
}

// Confirm a payment waiting in To review. A tap without an amount (Octopus) sends the amount the
// student typed (`raw`); nothing is saved without it, and the server's typo check asks first.
export async function confirmInbox(id, category, raw) {
  if (state.saving) return;
  const item = (state.data.inbox || []).find((i) => i.id === id);
  if (!item) return;
  let cents = item.amount;
  const draft = reviewDraft(id);
  if (item.amountUnknown) {
    raw = String(raw ?? draft.raw);
    cents = parseAmount(raw);
    const error = reviewAmountError(cents);
    state.review[id] = { ...draft, raw, error };
    if (error) {
      render();
      document.getElementById(`review-amount-${id}`)?.focus();
      return;
    }
  }
  state.saving = true;
  try {
    const data = await api("/api/inbox/confirm", confirmBody(item, category, raw, typoAnswered(draft, raw)));
    state.saving = false;
    if (data.needsTypoCheck) {
      state.review[id] = { ...state.review[id], typo: data.typo.reason, typoFor: raw.trim() };
      applyState(data.state);
      render();
      document.querySelector(`[data-review-confirm="${id}"]`)?.focus();
      return;
    }
    if (data.needsConfirm) {
      state.sheet = {
        level: data.level,
        options: data.options,
        selected: defaultChoice(data.options),
        amount: cents,
        fundsNow: data.state.view.fundsNow,
        tomorrow: data.state.view.tomorrow,
        todayRemaining: data.state.view.todayRemaining,
        category,
        inboxId: id,
        inboxItem: item,
        amountRaw: raw,
      };
      applyState(data.state);
      render();
      return;
    }
    delete state.review[id];
    savedDirect(data);
  } catch (err) {
    state.saving = false;
    if (item.amountUnknown && err.fromServer) state.review[id] = { ...state.review[id], error: paymentError(err) };
    else state.error = paymentError(err);
    render();
  }
}

export async function dismissInbox(id) {
  try {
    delete state.review[id];
    applyState(await api("/api/inbox/dismiss", { id }));
    showToast({ text: "Dismissed. Nothing was saved." });
  } catch (err) {
    state.error = err.message;
  }
  render();
}

export async function applyNumbers() {
  const body = {};
  state.fundDraft = {};
  for (const [id] of FUND_FIELDS) {
    body[id] = document.getElementById(id).value;
    state.fundDraft[id] = body[id];
  }
  state.fundDraft.total = document.getElementById("week-total")?.value ?? "";
  const bad = FUND_FIELDS.find(([id]) => parseAmount(body[id], true) == null);
  if (bad) {
    state.error = "Enter an amount of 0 or more, like 120 or 45.50.";
    state.errorField = bad[0];
    render();
    document.getElementById(bad[0])?.focus();
    return;
  }
  const mismatch = budgetMismatch();
  if (mismatch) {
    state.error = mismatch;
    state.errorField = null;
    render();
    document.getElementById("week-total")?.focus();
    return;
  }
  try {
    const data = await api("/api/settings", body);
    applyState(data, { error: "", errorField: null, fundDraft: null, screen: "today", showNotice: false, past: null });
    showToast({ text: "Weekly budget saved." });
    render();
  } catch (err) {
    state.error = fundError(err);
    state.errorField = err.field;
    render();
    if (err.field) document.getElementById(err.field)?.focus();
  }
}

// Save the map's campus for this mode, then reload the places around it.
export async function chooseCampus(campus) {
  if (campus === state.data.campus) return;
  const token = ++mapToken;
  try {
    const data = await api("/api/campus", { campus });
    if (token !== mapToken || data.mode !== state.data.mode) return;
    applyState(data);
  } catch (err) {
    state.error = err.message;
    render();
    return;
  }
  loadMap();
}

export async function loadMap() {
  const token = ++mapToken;
  state.screen = "map";
  state.mapLoading = true;
  state.error = "";
  state.selectedId = "";
  render();
  try {
    const data = await api(`/api/places?kind=${encodeURIComponent(state.mapKind)}&radius=${encodeURIComponent(state.mapRadius)}`);
    if (token !== mapToken) return;
    state.map = data;
    state.error = "";
  } catch (err) {
    if (token !== mapToken) return;
    state.map = null;
    state.error = err.message;
  }
  state.mapLoading = false;
  if (state.screen === "map") render();
}

// A receipt read in the camera screen: Add payment opens pre-filled. Never saves: the student
// checks the amount and the fund and taps Save as usual.
export function prefillAdd({ amount, category, note, scan }) {
  state.draft = { amount: plainAmount(amount), category, note: note || "" };
  state.scan = scan || null;
  state.attempt = null;
  state.error = "";
  state.sheet = null;
  state.undoId = null;
  state.adding = true;
  render();
  document.getElementById("amount")?.focus();
}

// From the quick-add widget: fill the Add sheet with the entry and save it the usual way.
// Returns "saved", "confirm" (the cover step is waiting in the app) or an error.
export async function quickAdd({ amount, category, note }) {
  if (state.saving) return "Still saving the last payment.";
  state.screen = state.screen === "settings" ? "today" : state.screen;
  state.draft = { amount: plainAmount(amount), category, note: note || "" };
  state.attempt = null;
  state.error = "";
  state.sheet = null;
  state.adding = true;
  render();
  await onSave();
  if (state.sheet) return "confirm";
  if (state.adding && state.error) return state.error;
  return "saved";
}

// Feedback tab: load the latest feedback, then send stars and words.
export async function loadFeedback() {
  try {
    const data = await api("/api/feedback");
    state.feedback.list = data.feedback;
  } catch (err) {
    state.feedback.list = [];
    state.feedback.error = err.message;
  }
  if (state.screen === "feedback") render();
}

export async function sendFeedback() {
  const f = state.feedback;
  if (f.sending) return;
  const box = document.getElementById("feedback-text");
  f.text = box ? box.value : f.text;
  if (!f.rating) {
    f.error = "Tap 1 to 5 stars first.";
    render();
    return;
  }
  f.sending = true;
  f.error = "";
  f.sent = false;
  render();
  try {
    const data = await api("/api/feedback", { rating: f.rating, text: f.text });
    Object.assign(f, { list: data.feedback, rating: 0, text: "", sent: true });
  } catch (err) {
    f.error = err.fromServer ? err.message : "Could not send it. Check your connection and try again.";
  }
  f.sending = false;
  render();
}
