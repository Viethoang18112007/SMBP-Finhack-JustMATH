// Rows and small blocks shared by several screens.

import { FUND_NAME, escapeHtml, hk, labelOf } from "../format.js";
import { state } from "../store.js";

// A payment row: what it was (the note, or the fund), the fund and any other fund that paid
// part of it, the amount, and Undo. With `undo` ({ confirming: id or null }), this week's
// payments get an Undo button, then an explicit "Yes, undo" / "Keep" step under the row.
// There is no edit: undo, then enter it again.
export function paymentRow(p, undo = null) {
  const from = p.from || {};
  const parts = [p.note ? labelOf(p.category) : ""];
  for (const fund of ["snack", "experience", "development", "savings"]) {
    if (from[fund] > 0 && p.category !== fund) parts.push(`${hk(from[fund])} from ${FUND_NAME[fund]}`);
  }
  if (p.uncovered > 0) parts.push(`${hk(p.uncovered)} not covered`);
  const sub = parts.filter(Boolean).join(" · ");
  const title = p.note || labelOf(p.category);
  let action = "";
  let confirm = "";
  if (undo) {
    const what = `${hk(p.amount)} ${labelOf(p.category)} payment`;
    if (undo.confirming === p.id) {
      confirm = `<div class="undo-confirm" role="group" aria-label="Undo the ${escapeHtml(what)}?"><span>Undo this payment?</span>`
        + `<button class="danger small" type="button" data-undo-yes="${p.id}">Yes, undo</button>`
        + `<button class="ghost small" type="button" data-undo-no>Keep</button></div>`;
    } else {
      action = `<button class="ghost small" type="button" data-undo="${p.id}" aria-label="Undo the ${escapeHtml(what)}">Undo</button>`;
    }
  }
  return `<div class="row payment" data-key="p-${p.id}">`
    + `<div class="pay-main"><strong>${escapeHtml(title)}</strong>${sub ? `<span class="tag">${escapeHtml(sub)}</span>` : ""}</div>`
    + `<span class="num pay-amt">${hk(p.amount)}</span>${action}${confirm}</div>`;
}

// An error from the server (a failed undo, a mode switch), shown on the screen. While the Add
// sheet is open, its errors belong to the sheet.
export function screenError() {
  if (!state.error || state.adding) return "";
  return `<div class="error-box" role="alert" data-key="error-${escapeHtml(state.error)}">${escapeHtml(state.error)}</div>`;
}
