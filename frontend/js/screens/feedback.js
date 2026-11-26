// Feedback (the last tab): 1 to 5 stars and a few words about the app (POST /api/feedback).
// Private: it goes to the central SSUST feedback server, only the team can read it, and the app
// lists nobody's feedback (feedback.py). Only a thank-you comes back.

import { escapeHtml } from "../format.js";
import { state } from "../store.js";

const STAR = '<svg viewBox="0 0 24 24" width="30" height="30" aria-hidden="true" fill="currentColor"><path d="M12 2.6l2.9 5.9 6.5.9-4.7 4.6 1.1 6.4L12 17.4l-5.8 3 1.1-6.4-4.7-4.6 6.5-.9z"/></svg>';
const WORDS = ["", "Not good", "Could be better", "OK", "Good", "Love it"];

export function feedbackScreen() {
  const f = state.feedback;
  const stars = [1, 2, 3, 4, 5].map((n) =>
    `<button type="button" class="rate${n <= f.rating ? " on" : ""}" data-rating="${n}" aria-pressed="${n === f.rating}" aria-label="${n} of 5: ${WORDS[n]}">${STAR}</button>`
  ).join("");
  const busy = f.sending ? ' disabled aria-busy="true"' : "";
  return `<section class="card" aria-labelledby="feedback-title">
      <h2 class="title" id="feedback-title">Feedback</h2>
      <p class="sub">How is SSUST working for you? Tell us what helps and what to change.</p>
      <p class="hint">Private: Only the SSUST team can read it. No name or account is sent, and your budget stays on your device.</p>
      <div class="rating" role="group" aria-label="Your rating">${stars}</div>
      <p class="rating-word" aria-live="polite">${escapeHtml(WORDS[f.rating] || "Tap a star")}</p>
      <label class="label" for="feedback-text">Your words <span class="opt">optional</span></label>
      <textarea id="feedback-text" class="feedback-input" maxlength="500" rows="4" placeholder="e.g. The map helped me find cheaper lunch">${escapeHtml(f.text)}</textarea>
      <div class="error" role="alert">${escapeHtml(f.error)}</div>
      <button class="primary" id="send-feedback" type="button"${busy}>${f.sending ? "Sending…" : "Send feedback"}</button>
      ${f.sent ? `<p class="hint" role="status">${escapeHtml(f.thanks || "Thanks! Only the SSUST team can read this.")}</p>` : ""}
    </section>`;
}
