// Feedback (the last tab): 1 to 5 stars and a few words about the app, saved on the server
// (POST /api/feedback), then the feedback already sent from this app.

import { escapeHtml, shortDate } from "../format.js";
import { state } from "../store.js";

const STAR = '<svg viewBox="0 0 24 24" width="30" height="30" aria-hidden="true" fill="currentColor"><path d="M12 2.6l2.9 5.9 6.5.9-4.7 4.6 1.1 6.4L12 17.4l-5.8 3 1.1-6.4-4.7-4.6 6.5-.9z"/></svg>';
const WORDS = ["", "Not good", "Could be better", "OK", "Good", "Love it"];

function sentList(list) {
  if (list == null) return `<p class="empty-line" role="status">Loading…</p>`;
  if (!list.length) return `<p class="empty-line">Nothing sent yet.</p>`;
  return `<ul class="feedback-list">${list.map((item) =>
    `<li><span class="feedback-meta">${"★".repeat(item.rating)}${"☆".repeat(5 - item.rating)} · ${escapeHtml(shortDate(item.createdAt.slice(0, 10)))}</span>`
    + `${item.text ? `<span class="feedback-text">${escapeHtml(item.text)}</span>` : ""}</li>`
  ).join("")}</ul>`;
}

export function feedbackScreen() {
  const f = state.feedback;
  const stars = [1, 2, 3, 4, 5].map((n) =>
    `<button type="button" class="rate${n <= f.rating ? " on" : ""}" data-rating="${n}" aria-pressed="${n === f.rating}" aria-label="${n} of 5: ${WORDS[n]}">${STAR}</button>`
  ).join("");
  const busy = f.sending ? ' disabled aria-busy="true"' : "";
  return `<section class="card" aria-labelledby="feedback-title">
      <h2 class="title" id="feedback-title">Feedback</h2>
      <p class="sub">How is SSUST working for you? Tell us what helps and what to change.</p>
      <div class="rating" role="group" aria-label="Your rating">${stars}</div>
      <p class="rating-word" aria-live="polite">${escapeHtml(WORDS[f.rating] || "Tap a star")}</p>
      <label class="label" for="feedback-text">Your words <span class="opt">optional</span></label>
      <textarea id="feedback-text" class="feedback-input" maxlength="500" rows="4" placeholder="e.g. The map helped me find cheaper lunch">${escapeHtml(f.text)}</textarea>
      <div class="error" role="alert">${escapeHtml(f.error)}</div>
      <button class="primary" id="send-feedback" type="button"${busy}>${f.sending ? "Sending…" : "Send feedback"}</button>
      ${f.sent ? `<p class="hint" role="status">Thank you, it was sent.</p>` : ""}
    </section>
    <section class="card" aria-labelledby="sent-title">
      <h2 class="title" id="sent-title">Recent feedback</h2>
      ${sentList(f.list)}
    </section>`;
}
