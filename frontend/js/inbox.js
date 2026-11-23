// Connected payments, SIMULATED in this demo. Real Wallet, Octopus or bank access is not
// available to us, so a "tap" here is a sample payment added to a real server inbox
// (POST /api/inbox). The student reviews each one on Today; Confirm goes through exactly the
// same payment logic as Add payment (overspend step included). Nothing here reads a bank.

import { notifyArrival } from "./notifications.js";
import { CATEGORIES, escapeHtml, hk, newRequestId } from "./format.js";
import { previewLine } from "./preview.js";
import { state } from "./store.js";

export const SOURCES = {
  apple_pay: { name: "Apple Pay", setting: "Apple Wallet" },
  octopus: { name: "Octopus", setting: "Octopus" },
  hsbc: { name: "HSBC", setting: "HSBC" },
  // Real Apple Pay payments sent by an iOS Shortcuts automation (not a simulated switch).
  wallet: { name: "Apple Pay", setting: "Apple Pay (Shortcuts)" },
};
export const SOURCE_ORDER = ["apple_pay", "octopus", "hsbc"];

// Sample taps per source: fictional or generic merchants, sample amounts.
const PRESETS = {
  apple_pay: [
    { merchant: "Sample Coffee Kiosk", amount: "38", card: "Sample card 0000" },
    { merchant: "Sample Noodle Bar", amount: "52", card: "Sample card 0000" },
  ],
  octopus: [
    { merchant: "Sample Convenience Store", amount: "24.50", card: "Sample Octopus" },
    { merchant: "Sample Bakery", amount: "16", card: "Sample Octopus" },
  ],
  hsbc: [
    { merchant: "Sample Bookshop", amount: "120", card: "Sample debit card" },
  ],
};
const next = { apple_pay: 0, octopus: 0, hsbc: 0 };

// The auto-play starts every run from the first sample of each source.
export function resetTaps() {
  for (const source of Object.keys(next)) next[source] = 0;
}

export function nextTap(source) {
  const list = PRESETS[source];
  const preset = list[next[source] % list.length];
  next[source] += 1;
  return { source, ...preset, externalId: `tap-${newRequestId()}`.slice(0, 64) };
}

export function connectedSources() {
  const connected = (state.data && state.data.connected) || {};
  return SOURCE_ORDER.filter((source) => connected[source]);
}

// "Simulate a tap" buttons, one per connected source.
export function tapButtons(where) {
  const on = connectedSources();
  if (!on.length) return `<p class="hint">Turn one on to simulate a tap.</p>`;
  return `<div class="tap-buttons">${on.map((source) => `<button type="button" class="ghost small" data-tap="${source}" data-tap-where="${where}">Simulate an ${SOURCES[source].name} tap</button>`).join("")}</div>
    <p class="hint">Simulated: no card is charged.</p>`;
}

export function connectedCard() {
  const connected = (state.data && state.data.connected) || {};
  const rows = SOURCE_ORDER.map((source) => {
    const on = Boolean(connected[source]);
    return `<button type="button" class="toggle switch-row" data-connect="${source}" aria-pressed="${on}">
        <span class="connect-name">${SOURCES[source].setting}</span><span class="switch" aria-hidden="true"></span>
      </button>`;
  }).join("");
  return `<details class="card fold" id="connected-card">
      <summary><span class="title" id="connected-title">Connected payments</span><span class="sim-tag">Simulated</span></summary>
      ${rows}
      <p class="hint">Sample payments only. Nothing here reads your bank.</p>
      <div class="mt-12">${tapButtons("settings")}</div>
    </details>`;
}

function fundSelect(item) {
  const options = CATEGORIES.map(([id, name]) => `<option value="${id}"${id === item.suggestedFund ? " selected" : ""}>${name}</option>`).join("");
  return `<select class="review-fund" id="review-fund-${item.id}" data-review-fund="${item.id}" aria-label="Fund for ${escapeHtml(item.merchant)}">${options}</select>`;
}

// Today: "To review (n)", each incoming payment with its fund pre-selected, Confirm or Dismiss.
export function reviewCard() {
  const items = (state.data && state.data.inbox) || [];
  if (!items.length || !state.view || !state.view.ready) return "";
  const rows = items.map((item) => `<li class="review-item" data-key="r-${item.id}">
      <div class="review-top"><span class="review-source">${SOURCES[item.source].name}${item.source === "wallet" ? "" : '<span class="sim-tag">Simulated</span>'}</span><strong class="num">${hk(item.amount)}</strong></div>
      <div class="review-merchant">${escapeHtml(item.merchant)} <span class="muted">· ${escapeHtml(item.card)}</span></div>
      ${item.suggestedReason ? `<p class="hint review-why">Fund picked: ${escapeHtml(item.suggestedReason)}</p>` : ""}
      ${item.typo ? `<p class="review-typo" role="alert"><strong>Typo?</strong> ${escapeHtml(item.typo.reason)} Check the amount before you confirm.</p>` : ""}
      <div class="review-actions">${fundSelect(item)}
        <button type="button" class="primary small" data-review-confirm="${item.id}">${item.typo ? `Confirm ${hk(item.amount)} anyway` : "Confirm"}</button>
        <button type="button" class="ghost small" data-review-dismiss="${item.id}">Dismiss</button></div>
      <p class="preview" id="review-preview-${item.id}">${escapeHtml(previewLine(state.view, item.amount, item.suggestedFund))}</p>
    </li>`).join("");
  return `<section class="card review" id="review-card" aria-labelledby="review-title">
      <h2 class="title" id="review-title">To review (${items.length})</h2>
      <ul class="review-list">${rows}</ul>
    </section>`;
}

export function updateReviewPreview(select) {
  const item = (state.data.inbox || []).find((i) => String(i.id) === select.dataset.reviewFund);
  const el = document.getElementById(`review-preview-${select.dataset.reviewFund}`);
  if (item && el) el.textContent = previewLine(state.view, item.amount, select.value);
}

// The notification for a simulated payment (notifications.js shows it): it says Simulated and a
// tap opens the "To review" card.
export function paymentNote(item, mode) {
  return {
    key: `payment:${mode}:${item.id}`,
    app: SOURCES[item.source].name,
    tag: '<span class="sim-tag">Simulated</span>',
    title: `${hk(item.amount)} at ${item.merchant}`,
    body: "Tap to review. Simulated: no card, no bank.",
    open: { screen: "today", review: true },
  };
}

// A new tap always shows its banner (the triggers will not show it a second time).
export function showNotification(item) {
  notifyArrival(paymentNote(item, state.data ? state.data.mode : "demo"));
}

// The discreet demo controls beside the phone on desktop.
export function renderDeskSide() {
  const side = document.getElementById("desk-side");
  if (!side || !state.data) return;
  side.innerHTML = `<div class="desk-box"><strong>Demo controls</strong><span class="hint">Outside the phone. Simulated payments only.</span>${tapButtons("desk")}</div>`;
}
