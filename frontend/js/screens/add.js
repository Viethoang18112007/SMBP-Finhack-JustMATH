// The Add payment sheet: amount, fund, optional note, the consequence preview, then Save.
// It opens over the current screen; a payment bigger than what is left turns it into the
// reallocation step (sheet.js) before anything is saved.

import { CAMERA_OFF, CATEGORIES, RETAKE_HINT, escapeHtml, hk, parseAmount } from "../format.js";
import { previewLine } from "../preview.js";
import { nativeScanner } from "../scanner.js";
import { SCAN_FAILED } from "../scanerror.js";
import { state } from "../store.js";

// Quick amounts in HK$, and the slider range: 0 to max(2 x today's left, HK$500), HK$1 steps.
export const QUICK = [20, 35, 50, 80];

export function sliderMaxDollars(view) {
  const left = view && view.ready ? Math.max(view.todayRemaining, 0) : 0;
  return Math.max(Math.ceil((2 * left) / 100), 500);
}

export function addSheetHtml() {
  const cats = CATEGORIES.map(([id, name]) => {
    const on = state.draft.category === id;
    return `<button type="button" data-cat="${id}" class="${on ? "on" : ""}" aria-pressed="${on}">${name}</button>`;
  }).join("");
  const error = state.error;
  const preview = previewLine(state.view, parseAmount(state.draft.amount), state.draft.category);
  const max = sliderMaxDollars(state.view);
  const typed = parseAmount(state.draft.amount);
  const dollars = Math.min(Math.floor((typed || 0) / 100), max);
  const quick = QUICK.map((v) => `<button type="button" class="chip" data-quick="${v}">HK$${v}</button>`).join("");
  const scan = state.scan;
  const reading = scan && scan.status === "reading";
  const found = scan && scan.status === "found";
  let scanText = "";
  if (reading) scanText = scan.percent ? `${scan.words}: ${scan.percent}%` : `${scan.words}…`;
  else if (found) {
    scanText = scan.guess
      ? `No TOTAL line found: best guess, check it. Line used: "${scan.line}"`
      : `Read from receipt: check it. Line used: "${scan.line}"`;
    if (scan.reason) scanText += `. Fund: ${scan.reason}`;
    if (scan.typo) scanText += `. Typo? ${scan.typo}`;
  }
  else if (scan && scan.status === "none") scanText = scan.reason === "no_amounts" ? RETAKE_HINT : "Could not read a total, type it in.";
  else if (scan && scan.status === "error") scanText = scan.message || SCAN_FAILED;
  else if (scan && scan.status === "camera_off") scanText = CAMERA_OFF;
  // The text that was read, folded under the scan row: always after the phone read it (in the iPhone
  // app, also when a total was found, so a wrong pick can be checked), and on the web when nothing was found.
  const phoneRead = scan && scan.phone && typeof scan.text === "string";
  const seen = scan && (scan.status === "none" || phoneRead)
    ? `<details class="more ocr-seen"><summary>${scan.phone ? "What the phone read" : "What the reader saw"}</summary><pre class="ocr-text">${escapeHtml(scan.text || "(no text at all: try more light, closer, flat)")}</pre></details>`
    : "";
  const scanRow = `<div class="scan-row">
      <button type="button" class="ghost small scan-btn" id="scan-btn"${reading ? ' disabled aria-busy="true"' : ""}>${reading ? '<span class="spinner" aria-hidden="true"></span>Reading…' : "Scan receipt"}</button>
      ${nativeScanner() ? `<button type="button" class="ghost small scan-btn" id="scan-photo"${reading ? " disabled" : ""}>From photos</button>` : ""}
      <input type="file" id="scan-file" accept="image/*" hidden>
      <span class="scan-status${found ? " is-found" : ""}" id="scan-status" role="status" aria-live="polite">${escapeHtml(scanText)}</span>
    </div>${seen}`;
  const busy = state.saving ? ' disabled aria-busy="true"' : "";
  return `<div class="panel add-panel" role="dialog" aria-modal="true" aria-labelledby="add-title">
      <span class="grip" aria-hidden="true"></span>
      <h2 class="sheet-title" id="add-title">Add payment</h2>
      ${state.draft.place ? `<p class="hint place-line">Meal at ${escapeHtml(state.draft.place.name)}. It counts for your campus medal when it fits today's food money.</p>` : scanRow}
      <label class="amount-field${error ? " invalid" : ""}${found ? " from-receipt" : ""}" for="amount">
        <span class="cur" aria-hidden="true">HK$</span>
        <input class="amount" id="amount" inputmode="decimal" autocomplete="off" placeholder="0" value="${escapeHtml(state.draft.amount)}" aria-label="Amount in Hong Kong dollars" aria-describedby="amount-error preview"${error ? ' aria-invalid="true"' : ""}>
      </label>
      <input type="range" class="slider amount-slider" id="amount-slider" min="0" max="${max}" step="1" value="${dollars}" aria-label="Amount slider, in HK$" aria-valuetext="${hk(dollars * 100)}">
      <div class="quick" role="group" aria-label="Quick amounts">${quick}</div>
      <div class="error" id="amount-error" role="alert">${escapeHtml(error)}</div>
      <div class="label" id="fund-label">Fund</div>
      <div class="cats" role="group" aria-labelledby="fund-label">${cats}</div>
      <label class="label" for="note">Note <span class="opt">optional</span></label>
      <input class="note${found && scan.merchant ? " from-receipt" : ""}" id="note" maxlength="40" autocomplete="off" placeholder="e.g. lunch" value="${escapeHtml(state.draft.note)}">
      <p class="preview" id="preview" aria-live="polite">${escapeHtml(preview)}</p>
      <div class="stack">
        <button class="primary" id="save" type="button"${busy}>${state.saving ? '<span class="spinner" aria-hidden="true"></span>Saving…' : "Save"}</button>
        <button class="ghost quiet" id="cancel-add" data-close="add" type="button">Cancel</button>
      </div>
    </div>`;
}
