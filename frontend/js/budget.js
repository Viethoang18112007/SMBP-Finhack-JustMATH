// The weekly budget editor, used by Settings and by the first-week setup on Today.
//
// The student types a weekly total, then sets each fund either as a percent of that total or
// as an HK$ amount: the other one follows as they type. A suggested split (server:
// money.SUGGESTED_SPLIT) is shown beside each fund and can be applied in one tap; a fund below
// its suggested minimum (money.MIN_SPLIT, e.g. Long-term Savings 10%) gets a soft warning only.
// What is saved is the HK$ amount per fund, and the amounts must add up to the total.
// All money is integer cents; percents are shown to one decimal.

import { FLEX_FUNDS, FUND_FIELDS, FUND_NAME, FUND_ORDER, escapeHtml, hk, parseAmount, plainAmount } from "./format.js";
import { state } from "./store.js";

// Used only if the server sent no split (it always does).
const FALLBACK_SPLIT = { main: 40, snack: 5, fixed: 15, experience: 10, development: 10, savings: 20 };
const FALLBACK_MIN = { main: 25, snack: 0, fixed: 0, experience: 0, development: 0, savings: 10 };
// Demo only: a first week with nothing to start from gets this total with the suggested split.
// Live starts every fund at HK$0: the student sets their own numbers.
const FIRST_TOTAL = 150000;
// The weekly total slider goes from 0 to max(HK$5,000, twice the total) in HK$10 steps; each fund
// slider goes from 0 to the weekly total. Typing a bigger amount is still allowed: the slider
// then sits at its end.
const TOTAL_FLOOR = 500000;

function zeroAmounts() {
  const amounts = {};
  for (const fund of FUND_ORDER) amounts[fund] = 0;
  return amounts;
}

function totalMax(cents) {
  return Math.max(TOTAL_FLOOR, 2 * (cents || 0)) / 100;
}

// A fund slider's end: the weekly total, in whole HK$.
function fundMax(total) {
  return Math.floor(Math.max(total || 0, 0) / 100);
}

export function splitOf() {
  const split = state.data && state.data.split;
  return {
    suggested: (split && split.suggested) || FALLBACK_SPLIT,
    minimum: (split && split.minimum) || FALLBACK_MIN,
  };
}

// Cents per fund for `total` cents and whole percents summing to 100. The cents lost to
// rounding go to Long-term Savings, so the amounts always add up to the total.
export function splitAmounts(total, percents) {
  const amounts = {};
  let used = 0;
  for (const fund of FUND_ORDER) {
    amounts[fund] = Math.floor((total * percents[fund]) / 100);
    used += amounts[fund];
  }
  amounts.savings += total - used;
  return amounts;
}

// "20", "12.5", "0": a fund's share of the total, to one decimal, no trailing ".0".
export function percentText(amount, total) {
  if (!(total > 0) || amount == null) return "0";
  const tenths = Math.round((amount * 1000) / total);
  return tenths % 10 === 0 ? String(tenths / 10) : (tenths / 10).toFixed(1);
}

// A typed percent ("12", "12.5", "12%") as a number from 0 to 100, or null.
export function parsePercent(raw) {
  const cleaned = String(raw).replace("%", "").trim();
  if (!/^\d{1,3}(\.\d)?$/.test(cleaned)) return null;
  const value = Number(cleaned);
  return value <= 100 ? value : null;
}

// What the inputs start from: what was typed (kept after a refused save), this week's
// amounts, last week's (server prefill), else the suggested split of a first total.
function startValues(view) {
  const opening = state.data.opening;
  if (state.fundDraft) {
    const amounts = {};
    for (const fund of FUND_ORDER) amounts[fund] = parseAmount(state.fundDraft[fund] ?? "", true);
    const total = parseAmount(state.fundDraft.total ?? "", true);
    return { amounts, total: total ?? sum(amounts) };
  }
  if (view.ready) return { amounts: { ...opening }, total: sum(opening) };
  if (state.data.prefill) return { amounts: { ...state.data.prefill }, total: sum(state.data.prefill) };
  if (state.data.mode === "demo") return { amounts: splitAmounts(FIRST_TOTAL, splitOf().suggested), total: FIRST_TOTAL };
  return { amounts: zeroAmounts(), total: 0 };
}

function sum(amounts) {
  return FUND_ORDER.reduce((acc, fund) => acc + (amounts[fund] || 0), 0);
}

function minWarning(fund, amount, total) {
  const min = splitOf().minimum[fund] || 0;
  if (!min || !(total > 0) || amount == null || amount * 100 >= min * total) return "";
  return `Below the suggested minimum of ${min}%`;
}

function fundRow(id, name, amount, total, view) {
  const { suggested, minimum } = splitOf();
  const demo = state.data.mode === "demo";
  // Live keeps this week's payments, so a fund can't go below what it already paid for.
  const spent = !demo && view.ready ? state.data.opening[id] - view.fundsNow[id] : 0;
  const bad = state.error && state.errorField === id;
  const flex = FLEX_FUNDS.includes(id) ? ` <span class="chip-flex">Flexible</span>` : "";
  const min = minimum[id] ? ` · min ${minimum[id]}%` : "";
  const warn = minWarning(id, amount, total);
  const spentHint = spent > 0 && !bad ? `<div class="hint" id="${id}-hint">${hk(spent)} already spent: the lowest you can set</div>` : "";
  const error = bad ? `<div class="error" id="${id}-error" role="alert" data-key="ferr-${id}-${escapeHtml(state.error)}">${escapeHtml(state.error)}</div>` : "";
  const described = [`${id}-suggest`, spentHint && `${id}-hint`, bad && `${id}-error`].filter(Boolean).join(" ");
  return `<div class="budget-row" data-fund-row="${id}">
      <div class="budget-row-top">
        <label class="budget-name" for="${id}">${name}${flex}</label>
        <span class="budget-suggest" id="${id}-suggest">Suggested ${suggested[id]}%${min}</span>
      </div>
      <div class="budget-inputs">
        <div class="pct-input"><input id="${id}-pct" data-pct="${id}" inputmode="decimal" autocomplete="off" aria-label="${name} percent of the week" value="${escapeHtml(percentText(amount, total))}"><span class="cur" aria-hidden="true">%</span></div>
        <div class="money-input${bad ? " invalid" : ""}"><span class="cur" aria-hidden="true">HK$</span>`
    + `<input id="${id}" data-budget="${id}" inputmode="decimal" autocomplete="off" value="${amount == null ? "" : escapeHtml(plainAmount(amount))}"${bad ? ' aria-invalid="true"' : ""} aria-describedby="${described}"></div>
      </div>
      <input type="range" class="slider fc-${id}" id="${id}-slider" data-slider="${id}" data-min="${spent > 0 ? spent : 0}" min="0" max="${fundMax(total)}" step="10" value="${Math.floor((amount || 0) / 100)}" aria-label="${name} slider" aria-valuetext="${hk(amount || 0)}">
      <div class="budget-warn" id="${id}-warn" aria-live="polite">${escapeHtml(warn)}</div>
      ${spentHint}${error}
    </div>`;
}

export function budgetFields(view) {
  const { amounts, total } = startValues(view);
  const rows = FUND_FIELDS.map(([id, name]) => fundRow(id, name, amounts[id], total, view)).join("");
  const generalError = state.error && !FUND_FIELDS.some(([id]) => id === state.errorField) ? state.error : "";
  return `${stackHtml(amounts)}<div class="field budget-total-field">
      <label for="week-total">Money for this week</label>
      <div class="money-input big-input"><span class="cur" aria-hidden="true">HK$</span><input id="week-total" inputmode="decimal" autocomplete="off" value="${escapeHtml(plainAmount(total))}"></div>
      <input type="range" class="slider slider-total" id="week-total-slider" min="0" max="${totalMax(total)}" step="10" value="${Math.floor((total || 0) / 100)}" aria-label="Money for this week slider" aria-valuetext="${hk(total || 0)}">
    </div>
    <div class="budget-tools">
      <button class="ghost small" type="button" id="use-suggested">Use suggested split</button>
      <span class="hint">Set each fund in % or HK$. The other follows.</span>
    </div>
    <div class="budget-rows">${rows}</div>
    <div class="budget-foot" id="budget-foot" aria-live="polite">${footHtml(amounts, total)}</div>
    <div class="error" role="alert">${escapeHtml(generalError)}</div>`;
}

// The total funds bar: one stacked bar of the week split by fund, a legend with amounts, the total.
// Widths are set by paintStack through element.style (the CSP blocks inline style attributes).
function stackHtml(amounts) {
  const legend = FUND_ORDER.map((fund) => `<li><span class="sw fc-${fund}" aria-hidden="true"></span><span class="lg-name">${FUND_NAME[fund]}</span> <span class="num" data-legend="${fund}">${hk(amounts[fund] || 0)}</span></li>`).join("");
  const segs = FUND_ORDER.map((fund) => `<span class="seg fc-${fund}" data-seg="${fund}"></span>`).join("");
  return `<div class="stack-card">
      <div class="stack-head"><span class="label">Total funds this week</span><strong class="num stack-total" id="stack-total">${hk(sum(amounts))}</strong></div>
      <div class="stack-bar" id="stack-bar" role="img" aria-label="${escapeHtml(stackLabel(amounts))}">${segs}</div>
      <ul class="stack-legend">${legend}</ul>
    </div>`;
}

function stackLabel(amounts) {
  return `Total ${hk(sum(amounts))}: ` + FUND_ORDER.map((fund) => `${FUND_NAME[fund]} ${hk(amounts[fund] || 0)}`).join(", ");
}

// Called after every change: segment widths, legend, total, and the sliders follow the amounts.
export function paintStack(skip) {
  const bar = document.getElementById("stack-bar");
  if (!bar) return;
  const amounts = readAmounts();
  const clean = {};
  for (const fund of FUND_ORDER) clean[fund] = Math.max(amounts[fund] || 0, 0);
  const all = sum(clean);
  const weekTotal = readTotal() || 0;
  const totalSlider = document.getElementById("week-total-slider");
  if (totalSlider && totalSlider !== skip) {
    totalSlider.max = String(totalMax(weekTotal));
    totalSlider.value = String(Math.floor(weekTotal / 100));
  }
  if (totalSlider) totalSlider.setAttribute("aria-valuetext", hk(weekTotal));
  for (const fund of FUND_ORDER) {
    const seg = bar.querySelector(`[data-seg="${fund}"]`);
    if (seg) seg.style.width = all > 0 ? `${(clean[fund] * 100) / all}%` : "0%";
    const legend = document.querySelector(`[data-legend="${fund}"]`);
    if (legend) legend.textContent = hk(clean[fund]);
    const slider = document.getElementById(`${fund}-slider`);
    if (slider) slider.max = String(fundMax(weekTotal));
    if (slider && slider !== skip) slider.value = String(Math.floor(clean[fund] / 100));
    if (slider) slider.setAttribute("aria-valuetext", hk(clean[fund]));
  }
  bar.classList.toggle("is-empty", all === 0);
  bar.setAttribute("aria-label", stackLabel(clean));
  const total = document.getElementById("stack-total");
  if (total) total.textContent = hk(all);
}

// "100% assigned" or "HK$50 left to assign", with a quick fix that puts the rest in savings.
function footHtml(amounts, total) {
  const assigned = sum(amounts);
  const pct = percentText(assigned, total);
  if (total > 0 && assigned === total) {
    return `<span class="foot-ok">100% assigned</span><strong class="num" id="budget-total">${hk(total)}</strong>`;
  }
  const diff = total - assigned;
  const text = diff > 0 ? `${hk(diff)} left to assign` : `${hk(-diff)} more than the total`;
  const fix = diff > 0
    ? `<button class="ghost small" type="button" id="rest-to-savings">Put the rest in Long-term Savings</button>`
    : `<button class="ghost small" type="button" id="match-total">Make the total ${hk(assigned)}</button>`;
  return `<span class="foot-warn">${pct}% assigned · ${text}</span><strong class="num" id="budget-total">${hk(assigned)}</strong>${fix}`;
}

// Live editing, without a re-render, so focus and the caret stay where they are.
function readAmounts() {
  const amounts = {};
  for (const fund of FUND_ORDER) {
    const input = document.getElementById(fund);
    amounts[fund] = input ? parseAmount(input.value, true) : null;
  }
  return amounts;
}

function readTotal() {
  const input = document.getElementById("week-total");
  return input ? parseAmount(input.value, true) : null;
}

function refresh(skip) {
  paintStack(skip);
  const amounts = readAmounts();
  const total = readTotal() || 0;
  for (const fund of FUND_ORDER) {
    const pct = document.getElementById(`${fund}-pct`);
    if (pct && pct !== skip) pct.value = percentText(amounts[fund] || 0, total);
    const warn = document.getElementById(`${fund}-warn`);
    if (warn) warn.textContent = minWarning(fund, amounts[fund], total);
  }
  const foot = document.getElementById("budget-foot");
  if (foot) {
    const clean = {};
    for (const fund of FUND_ORDER) clean[fund] = amounts[fund] || 0;
    foot.innerHTML = footHtml(clean, total);
    bindFoot();
  }
}

function setAmounts(amounts) {
  for (const fund of FUND_ORDER) {
    const input = document.getElementById(fund);
    if (input) input.value = plainAmount(amounts[fund]);
  }
}

function bindFoot() {
  document.getElementById("rest-to-savings")?.addEventListener("click", () => {
    const amounts = readAmounts();
    const total = readTotal() || 0;
    const others = FUND_ORDER.filter((f) => f !== "savings").reduce((acc, f) => acc + (amounts[f] || 0), 0);
    document.getElementById("savings").value = plainAmount(Math.max(total - others, 0));
    refresh();
  });
  document.getElementById("match-total")?.addEventListener("click", () => {
    const amounts = readAmounts();
    document.getElementById("week-total").value = plainAmount(FUND_ORDER.reduce((acc, f) => acc + (amounts[f] || 0), 0));
    refresh();
  });
}

export function bindBudget() {
  const totalInput = document.getElementById("week-total");
  if (!totalInput) return;
  // A new total keeps each fund's percent and rescales the amounts. From a zero start (every
  // fund HK$0), the first total above 0 fills the suggested split.
  let lastTotal = readTotal() || 0;
  const onTotal = (skip) => {
    const total = readTotal();
    if (total == null) return;
    const amounts = readAmounts();
    if (total > 0 && sum(amounts) === 0) {
      setAmounts(splitAmounts(total, splitOf().suggested));
    } else if (lastTotal > 0) {
      const scaled = {};
      let used = 0;
      for (const fund of FUND_ORDER) {
        scaled[fund] = Math.floor(((amounts[fund] || 0) * total) / lastTotal);
        used += scaled[fund];
      }
      const assignedBefore = FUND_ORDER.reduce((acc, f) => acc + (amounts[f] || 0), 0);
      if (assignedBefore === lastTotal) scaled.savings += total - used; // keep it at 100%
      setAmounts(scaled);
    }
    lastTotal = total;
    refresh(skip);
  };
  totalInput.addEventListener("input", () => onTotal());
  document.getElementById("week-total-slider")?.addEventListener("input", (event) => {
    totalInput.value = plainAmount(Number(event.target.value) * 100);
    onTotal(event.target);
  });
  // A percent sets the amount from the total.
  document.querySelectorAll("[data-pct]").forEach((input) => input.addEventListener("input", () => {
    const pct = parsePercent(input.value);
    const total = readTotal();
    if (pct == null || total == null) return;
    document.getElementById(input.dataset.pct).value = plainAmount(Math.round((total * pct) / 100));
    refresh(input);
  }));
  // An amount updates its percent.
  document.querySelectorAll("[data-budget]").forEach((input) => input.addEventListener("input", () => refresh()));
  // A slider sets its fund in HK$10 steps, from 0 to the weekly total, never below what Live
  // already spent from it. The % and HK$ fields follow.
  document.querySelectorAll("[data-slider]").forEach((slider) => slider.addEventListener("input", () => {
    const fund = slider.dataset.slider;
    const field = document.getElementById(fund);
    if (!field) return;
    let cents = Number(slider.value) * 100;
    const floor = Number(slider.dataset.min) || 0;
    if (cents < floor) {
      cents = floor;
      slider.value = String(Math.ceil(floor / 100));
    }
    field.value = plainAmount(cents);
    refresh(slider);
  }));
  paintStack();
  document.getElementById("use-suggested")?.addEventListener("click", () => {
    const total = readTotal();
    if (total == null) return;
    setAmounts(splitAmounts(total, splitOf().suggested));
    refresh();
  });
  bindFoot();
}

// Checked before saving: the amounts must add up to the total typed at the top.
export function budgetMismatch() {
  const total = readTotal();
  if (total == null) return "Enter the money for this week, like 1500.";
  const amounts = readAmounts();
  if (FUND_ORDER.some((fund) => amounts[fund] == null)) return null; // the amount check reports it
  const assigned = FUND_ORDER.reduce((acc, f) => acc + amounts[f], 0);
  if (assigned === total) return null;
  return assigned < total
    ? `${hk(total - assigned)} is not in any fund yet. Add it to a fund, or tap "Put the rest in Long-term Savings".`
    : `The funds add up to ${hk(assigned - total)} more than this week's ${hk(total)}.`;
}
