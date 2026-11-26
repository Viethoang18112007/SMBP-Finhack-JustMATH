// Feedback, private by design: the app only ever sends it (POST /api/feedback) and shows
// "Thanks". It never asks the server for a list: only the team can read feedback, with the
// admin token (README, "Feedback (private)").
//
// The Feedback tab (screens/feedback.js) and the Rate this control below send through here, with
// an anonymous id for this browser (32 random hex characters kept in localStorage, so the team can
// tell repeat senders apart without knowing who they are).

import { api } from "./api.js";
import { setHtml } from "./closers.js";
import { escapeHtml } from "./format.js";

const DEVICE_KEY = "ssust.deviceId";
const MAX_MESSAGE = 500;

// The anonymous id for this browser, made once; null when storage is blocked.
export function deviceId() {
  try {
    let id = window.localStorage.getItem(DEVICE_KEY);
    if (!/^[0-9a-f]{32}$/.test(id || "")) {
      const bytes = new Uint8Array(16);
      window.crypto.getRandomValues(bytes);
      id = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
      window.localStorage.setItem(DEVICE_KEY, id);
    }
    return id;
  } catch (err) {
    return null;
  }
}

// One entry to the team. Returns the server's answer ({ok, id, thanks}); throws with a message.
export function sendFeedback({ rating = null, message = "", screen, contextId = null, withDevice = true }) {
  const body = { screen };
  if (rating) body.rating = rating;
  if (message) body.message = message;
  if (contextId) body.contextId = contextId;
  const id = withDevice ? deviceId() : null;
  if (id) body.deviceId = id;
  return api("/api/feedback", body);
}

// "Rate this": a small three-level control (good / so-so / not right) under a receipt reading,
// the This week card and a grocery estimate. One tap sends a rating (5, 3 or 1) with the
// context id through the same private pipeline; then an optional comment box appears below.
// Screens only place a slot: <div data-rate-slot="receipt" data-context="receipt:..."
// data-question="Is the reading correct?"></div>. A MutationObserver fills every slot after any
// render, so no screen needs to call anything. No page reload, nothing blocks.

const rated = new Map(); // "screen|context" -> { rating, sent, sending, error }

function rateKey(screen, context) {
  return `${screen}|${context}`;
}

export function rateHtml(screen, context, question) {
  const r = rated.get(rateKey(screen, context));
  if (!r) {
    return `<div class="rt" role="group" aria-label="${escapeHtml(question)}"><span class="rt-q">${escapeHtml(question)}</span>`
      + `<button type="button" class="rt-btn" data-rate="5" aria-label="Yes" title="Yes">👍</button>`
      + `<button type="button" class="rt-btn" data-rate="3" aria-label="So-so" title="So-so">😐</button>`
      + `<button type="button" class="rt-btn" data-rate="1" aria-label="No" title="No">👎</button></div>`;
  }
  if (r.sent) return `<p class="rt rt-done" role="status">Thanks for the feedback.</p>`;
  const error = r.error ? `<span class="error" role="alert">${escapeHtml(r.error)}</span>` : "";
  return `<div class="rt rt-more"><span class="rt-q">Thanks! Anything to add? (optional)</span>
      <textarea class="rt-text" data-rate-comment maxlength="${MAX_MESSAGE}" rows="2" aria-label="Comment (optional)"></textarea>
      <div class="rt-row"><button type="button" class="ghost small" data-rate-send${r.sending ? " disabled" : ""}>Send comment</button>
      <button type="button" class="ghost small quiet" data-rate-close>No thanks</button>${error}</div></div>`;
}

function fillSlot(slot) {
  setHtml(slot, rateHtml(slot.dataset.rateSlot, slot.dataset.context || "", slot.dataset.question || "Is this useful?"));
}

function fillSlots(root = document) {
  root.querySelectorAll("[data-rate-slot]").forEach(fillSlot);
}

function slotOf(el) {
  const slot = el.closest("[data-rate-slot]");
  return slot ? { slot, key: rateKey(slot.dataset.rateSlot, slot.dataset.context || "") } : null;
}

async function sendRate(slot, entry, message) {
  const context = slot.dataset.context || null;
  try {
    // A comment is a second entry with the same context and no rating, so no rating counts twice.
    await sendFeedback({ rating: message ? null : entry.rating, message: message || "", screen: slot.dataset.rateSlot, contextId: context });
    return true;
  } catch (err) {
    entry.error = err.message;
    return false;
  }
}

document.addEventListener("click", async (event) => {
  const btn = event.target.closest("[data-rate], [data-rate-send], [data-rate-close]");
  if (!btn) return;
  const found = slotOf(btn);
  if (!found) return;
  const { slot, key } = found;
  if (btn.dataset.rate) {
    const entry = { rating: Number(btn.dataset.rate), sent: false, sending: false, error: "" };
    rated.set(key, entry);
    fillSlot(slot); // the comment box appears at once; the rating goes out in the background
    if (!(await sendRate(slot, entry, ""))) {
      rated.delete(key);
      fillSlot(slot);
    }
    return;
  }
  const entry = rated.get(key);
  if (!entry) return;
  if ("rateClose" in btn.dataset) {
    entry.sent = true;
    fillSlot(slot);
    return;
  }
  const text = slot.querySelector("[data-rate-comment]")?.value.trim() || "";
  if (!text) {
    entry.sent = true;
    fillSlot(slot);
    return;
  }
  entry.sending = true;
  fillSlot(slot);
  const ok = await sendRate(slot, entry, text);
  entry.sending = false;
  entry.sent = ok;
  document.querySelectorAll("[data-rate-slot]").forEach((s) => { if (slotOf(s)?.key === key) fillSlot(s); });
});

// Fill slots after any render (screens, widgets, the camera sheet), and on request.
let slotTimer = 0;
if (typeof MutationObserver === "function") {
  new MutationObserver(() => {
    if (slotTimer) return;
    slotTimer = requestAnimationFrame(() => {
      slotTimer = 0;
      fillSlots();
    });
  }).observe(document.body, { childList: true, subtree: true });
}
document.addEventListener("ssust:rate-slots", () => fillSlots());
