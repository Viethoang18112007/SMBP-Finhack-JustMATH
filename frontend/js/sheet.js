// The reallocation step of the Add sheet, shown when a payment is bigger than what is left.
//
// Nothing is saved until one option is picked and Confirm is pressed. Each option card says
// where the extra comes from and what tomorrow's food money becomes; the fund before/after
// list is one tap away ("What changes"). Fixed Bills is never offered (the server never makes
// it a cover). Long-term Savings is listed last and marked as the last resort. No money moves:
// it only shifts budget between the student's own funds.

import { FUND_NAME, escapeHtml, hk, labelOf } from "./format.js";

const ORDER = { snack: 0, flex: 1, savings: 2 };
const FUNDS_SHOWN = ["main", "snack", "experience", "development", "savings"];

// Snacks first, then Experience/Development, then Long-term Savings last.
export function sortedOptions(options) {
  return options.slice().sort((a, b) => (ORDER[a.choice] ?? 9) - (ORDER[b.choice] ?? 9));
}

export function defaultChoice(options) {
  const sorted = sortedOptions(options);
  return sorted.length ? sorted[0].choice : null;
}

function gapOf(options) {
  const first = options[0];
  return first ? Object.values(first.cover || {}).reduce((sum, cents) => sum + cents, 0) : 0;
}

function coverText(opt) {
  return Object.entries(opt.cover || {})
    .map(([fund, cents]) => `${hk(cents)} from ${FUND_NAME[fund]}`)
    .join(" + ");
}

function coverTotal(opt) {
  return Object.values(opt.cover || {}).reduce((sum, cents) => sum + cents, 0);
}

// "Take HK$8 from Snacks", "Take HK$8 from flexible funds" (Experience, then Development).
export function optionTitle(opt) {
  if (opt.choice === "flex") return `Take ${hk(coverTotal(opt))} from flexible funds`;
  return `Take ${coverText(opt)}`;
}

// Under a flexible option: which flexible fund pays what, e.g. "Experience HK$5 + Development HK$3".
function flexDetail(opt) {
  if (opt.choice !== "flex") return "";
  const parts = Object.entries(opt.cover || {}).map(([fund, cents]) => `${FUND_NAME[fund]} ${hk(cents)}`);
  return parts.length ? `<span class="option-detail">${escapeHtml(parts.join(" + "))}</span>` : "";
}

function fundsOf(opt) {
  if (opt.choice === "flex") return "flexible funds";
  return Object.keys(opt.cover || {}).map((fund) => FUND_NAME[fund]).join(" + ");
}

function moves(opt, sheet) {
  return FUNDS_SHOWN
    .filter((fund) => (opt.from[fund] || 0) > 0)
    .map((fund) => `<li><span>${FUND_NAME[fund]}</span><span class="num">${hk(sheet.fundsNow[fund])} → ${hk(opt.fundsAfter[fund])}</span></li>`)
    .join("");
}

function tomorrowText(opt, sheet) {
  return opt.tomorrowAfter === sheet.tomorrow
    ? `Tomorrow stays ${hk(sheet.tomorrow)}`
    : `Tomorrow: ${hk(sheet.tomorrow)} → ${hk(opt.tomorrowAfter)}`;
}

function optionHtml(opt, sheet, recommended) {
  const last = opt.choice === "savings";
  const on = opt.choice === sheet.selected;
  let badge = "";
  if (last) badge = ` <span class="badge last">Last resort</span>`;
  else if (opt.choice === recommended) badge = ` <span class="badge rec">Recommended</span>`;
  return `<label class="option${last ? " last-resort" : ""}${on ? " on" : ""}" data-option="${escapeHtml(opt.choice)}">
      <input type="radio" name="cover" value="${escapeHtml(opt.choice)}"${on ? " checked" : ""}>
      <span class="option-body">
        <span class="option-cover">${escapeHtml(optionTitle(opt))}${badge}</span>
        ${flexDetail(opt)}
        <span class="option-tomorrow">${escapeHtml(tomorrowText(opt, sheet))}</span>
      </span>
    </label>`;
}

export function confirmLabel(sheet) {
  const opt = sheet.options.find((o) => o.choice === sheet.selected);
  return opt ? `Confirm · from ${fundsOf(opt)}` : "Pick an option";
}

function changesHtml(sheet) {
  const opt = sheet.options.find((o) => o.choice === sheet.selected);
  return opt ? `<ul class="moves">${moves(opt, sheet)}</ul>` : "";
}

export function sheetHtml(sheet) {
  const options = sortedOptions(sheet.options);
  const gap = gapOf(options);
  const what = `${hk(sheet.amount)} ${labelOf(sheet.category)} payment`;
  const food = sheet.category === "main" || sheet.category === "snack";
  const intro = food
    ? `${what}, ${hk(Math.max(sheet.todayRemaining, 0))} left today.`
    : `${what}, ${hk(sheet.fundsNow[sheet.category])} left in ${FUND_NAME[sheet.category]}.`;
  const selected = options.find((o) => o.choice === sheet.selected);
  const danger = selected && selected.choice === "savings";
  const recommended = defaultChoice(options);
  return `<div class="panel level-${sheet.level}" role="dialog" aria-modal="true" aria-labelledby="sheet-title" aria-describedby="sheet-intro">
    <span class="grip" aria-hidden="true"></span>
    <h2 class="sheet-title" id="sheet-title">Where should the extra ${hk(gap)} come from?</h2>
    <p class="sheet-intro" id="sheet-intro">${escapeHtml(intro)}</p>
    <fieldset class="options"><legend class="sr-only">Where the extra ${hk(gap)} comes from</legend>
      ${options.map((opt) => optionHtml(opt, sheet, recommended)).join("")}
    </fieldset>
    <details class="changes"><summary>What changes</summary><div id="changes">${changesHtml(sheet)}</div></details>
    <p class="fine">Nothing is saved until you confirm.</p>
    <div class="stack">
      <button class="${danger ? "danger" : "primary"}" id="confirm-cover" type="button"${selected ? "" : " disabled"}>${escapeHtml(confirmLabel(sheet))}</button>
      <button class="ghost quiet" id="dismiss" data-close="sheet" type="button">Back</button>
    </div>
  </div>`;
}

// Picking an option only updates the modal in place, so focus stays on the radio.
export function selectOption(sheetEl, sheet, choice) {
  sheet.selected = choice;
  sheetEl.querySelectorAll("[data-option]").forEach((el) => el.classList.toggle("on", el.dataset.option === choice));
  const changes = sheetEl.querySelector("#changes");
  if (changes) changes.innerHTML = changesHtml(sheet);
  const confirm = sheetEl.querySelector("#confirm-cover");
  if (!confirm) return;
  confirm.textContent = confirmLabel(sheet);
  confirm.disabled = false;
  confirm.className = choice === "savings" ? "danger" : "primary";
}

// Keep Tab inside the sheet.
export function trapFocus(event, container) {
  const items = [...container.querySelectorAll("button:not([disabled]), input:not([disabled]), summary")]
    .filter((el) => !(el.type === "radio" && !el.checked));
  if (!items.length) return;
  const first = items[0];
  const last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    last.focus();
    event.preventDefault();
  } else if (!event.shiftKey && document.activeElement === last) {
    first.focus();
    event.preventDefault();
  }
}
