// Feedback, private by design: the app only ever sends it (POST /api/feedback) and shows
// "Thanks". It never asks the server for a list: only the team can read feedback, with the
// admin token (README, "Feedback (private)").
//
// The Settings card: a 1 to 5 rating, an optional message, and an optional anonymous id for this
// browser (32 random hex characters kept in localStorage, so the team can tell repeat senders
// apart without knowing who they are). The card updates in place: no screen re-render.

import { api } from "./api.js";
import { setHtml } from "./closers.js";
import { escapeHtml } from "./format.js";

const DEVICE_KEY = "ssust.deviceId";
const MAX_MESSAGE = 500;
const THANKS = "Thanks! Only the SSUST team can read this.";

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

const card = { rating: 0, message: "", withDevice: true, sending: false, thanks: "", error: "" };

function starsHtml() {
  return [1, 2, 3, 4, 5].map((n) => {
    const on = n <= card.rating;
    return `<button type="button" class="fb-star${on ? " on" : ""}" data-fb-star="${n}" aria-pressed="${n === card.rating}" aria-label="${n} out of 5">★</button>`;
  }).join("");
}

function bodyHtml() {
  if (card.thanks) {
    return `<p class="fb-thanks" role="status">${escapeHtml(card.thanks)}</p>
      <button type="button" class="ghost small" data-fb-again>Send more feedback</button>`;
  }
  const ready = (card.rating > 0 || card.message.trim()) && !card.sending;
  return `<div class="fb-stars" role="group" aria-label="Your rating">${starsHtml()}</div>
    <label class="label" for="fb-message">Anything to tell us? (optional)</label>
    <textarea id="fb-message" data-fb-message maxlength="${MAX_MESSAGE}" rows="3" placeholder="What works, what does not">${escapeHtml(card.message)}</textarea>
    <label class="fb-check"><input type="checkbox" data-fb-device${card.withDevice ? " checked" : ""}> Include an anonymous id for this browser</label>
    ${card.error ? `<p class="error" role="alert">${escapeHtml(card.error)}</p>` : ""}
    <button type="button" class="primary" data-fb-send${ready ? "" : " disabled"}>${card.sending ? "Sending…" : "Send feedback"}</button>`;
}

export function feedbackCard() {
  return `<section class="card" id="feedback-card" aria-labelledby="fb-title">
      <h2 class="title" id="fb-title">Feedback</h2>
      <p class="sub">Private: only the SSUST team can read it. No name or account is sent.</p>
      <div data-fb-body>${bodyHtml()}</div>
    </section>`;
}

// Redraws the card body only, keeping the focus and the caret in the message box.
function paint() {
  const box = document.querySelector("[data-fb-body]");
  if (!box) return;
  const typing = document.activeElement && document.activeElement.id === "fb-message";
  const caret = typing ? document.activeElement.selectionStart : null;
  if (!setHtml(box, bodyHtml())) return;
  if (typing) {
    const area = document.getElementById("fb-message");
    area?.focus();
    area?.setSelectionRange(caret, caret);
  }
}

async function send() {
  if (card.sending || !(card.rating > 0 || card.message.trim())) return;
  card.sending = true;
  card.error = "";
  paint();
  try {
    const answer = await sendFeedback({ rating: card.rating || null, message: card.message.trim(), screen: "settings", withDevice: card.withDevice });
    card.thanks = answer.thanks || THANKS;
    card.rating = 0;
    card.message = "";
  } catch (err) {
    card.error = err.message;
  }
  card.sending = false;
  paint();
  document.querySelector("[data-fb-again], [data-fb-send]")?.focus();
}

document.addEventListener("click", (event) => {
  const star = event.target.closest("[data-fb-star]");
  if (star) {
    const n = Number(star.dataset.fbStar);
    card.rating = card.rating === n ? 0 : n;
    card.error = "";
    paint();
    document.querySelector(`[data-fb-star="${n}"]`)?.focus();
    return;
  }
  if (event.target.closest("[data-fb-send]")) {
    send();
    return;
  }
  if (event.target.closest("[data-fb-again]")) {
    card.thanks = "";
    paint();
    document.querySelector('[data-fb-star="1"]')?.focus();
  }
});

document.addEventListener("input", (event) => {
  if (event.target.matches?.("[data-fb-message]")) {
    const had = Boolean(card.message.trim());
    card.message = event.target.value.slice(0, MAX_MESSAGE);
    if (had !== Boolean(card.message.trim())) paint(); // Send turns on or off
  }
});

document.addEventListener("change", (event) => {
  if (event.target.matches?.("[data-fb-device]")) card.withDevice = event.target.checked;
});
