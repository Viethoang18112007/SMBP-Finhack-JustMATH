import { dayLabel, escapeHtml, hk } from "../format.js";
import { paymentsOn, shownWeek, state, sumOn } from "../store.js";
import { paymentRow, screenError } from "./rows.js";

export function dayScreen() {
  const date = state.day || state.data.today;
  const week = shownWeek();
  const items = paymentsOn(date, week);
  // Only the current week can change; a past week is read-only.
  const undo = week === state.data ? { confirming: state.undoId } : null;
  const total = sumOn(date, week);
  return `${screenError()}<section class="card" aria-labelledby="day-title">
    <div class="day-head">
      <button class="icon-btn" id="back-week" type="button" aria-label="Back to the week">
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>
      </button>
      <h2 class="title" id="day-title">${escapeHtml(dayLabel(date))}</h2>
      <span class="num day-total">${total ? hk(total) : ""}</span>
    </div>
    <div class="list">${items.length ? items.slice().reverse().map((p) => paymentRow(p, undo)).join("") : `<p class="empty-line">No payments on this day.</p>`}</div>
  </section>`;
}
