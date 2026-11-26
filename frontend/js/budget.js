// The weekly budget editor, used by Settings and by the first-week setup on Today.
//
// The student types a weekly total, then sets each fund either as a percent of that total, as an
// HK$ amount, or with its slider. Once there is a total, the six funds always add up to exactly
// that total: moving one fund moves the other (unlocked) ones proportionally, by the shared
// rules in split.js (the same as backend/ssust/split.py, tested together). A lock keeps a fund
// fixed while the others move. A suggested split (server: money.SUGGESTED_SPLIT) can be applied
// in one tap; a fund below its suggested minimum (money.MIN_SPLIT, e.g. Long-term Savings 10%)
// gets a soft warning only. In Live, a fund never goes below what it already paid for this week.
//
// Smooth dragging: slider input is applied once per animation frame and only the affected nodes
// change (no screen re-render). Nothing is sent to the server while dragging: on release the
// values are kept as a draft (state.fundDraft, debounced) so a re-render keeps them, and Save
// sends them. All money is integer cents; percents are shown to one decimal and add up to 100.

import { setHtml } from "./closers.js";
import { FLEX_FUNDS, FUND_FIELDS, FUND_NAME, FUND_ORDER, escapeHtml, hk, parseAmount, plainAmount } from "./format.js";
import { distribute, percents, rebalance } from "./split.js";
import { state } from "./store.js";

// Used only if the server sent no split (it always does).
const FALLBACK_SPLIT = { main: 40, snack: 5, fixed: 15, experience: 10, development: 10, savings: 20 };
const FALLBACK_MIN = { main: 25, snack: 0, fixed: 0, experience: 0, development: 0, savings: 10 };
// Demo only: a first week with nothing to start from gets this total with the suggested split.
// Live starts every fund at HK$0: the student sets their own numbers.
const FIRST_TOTAL = 150000;
// The weekly total slider goes from 0 to max(HK$5,000, twice the total) in HK$10 steps; each fund
// slider goes from 0 to the weekly total in HK$1 steps. Typing a bigger amount is still allowed:
// the slider then sits at its end.
const TOTAL_FLOOR = 500000;
const THUMB_PX = 28; // the slider thumb width in styles.css, to centre the value bubble on it
const DRAFT_MS = 250;

// Funds the student locked: they keep their amount while the others move (this browser tab only).
const locked = new Set();

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
  return tenthsText(tenths);
}

function tenthsText(tenths) {
  return tenths % 10 === 0 ? String(tenths / 10) : (tenths / 10).toFixed(1);
}

// The percent shown for every fund. When the funds add up to the total, the tenths are shared
// by largest remainder so the six shown percents add up to exactly 100 (33.4 + 33.3 + 33.3).
function percentTexts(amounts, total) {
  const clean = cleanAmounts(amounts);
  const texts = {};
  if (total > 0 && sum(clean) === total) {
    const tenths = percents(clean, total, 1000);
    for (const fund of FUND_ORDER) texts[fund] = tenthsText(tenths[fund]);
  } else {
    for (const fund of FUND_ORDER) texts[fund] = percentText(amounts[fund], total);
  }
  return texts;
}

// A typed percent ("12", "12.5", "12%") as a number from 0 to 100, or null.
export function parsePercent(raw) {
  const cleaned = String(raw).replace("%", "").trim();
  if (!/^\d{1,3}(\.\d)?$/.test(cleaned)) return null;
  const value = Number(cleaned);
  return value <= 100 ? value : null;
}

// What the inputs start from: what was typed (kept after a refused save, or a draft kept on
// release), this week's amounts, last week's (server prefill), else the suggested split.
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

function cleanAmounts(amounts) {
  const clean = {};
  for (const fund of FUND_ORDER) clean[fund] = Math.max(amounts[fund] || 0, 0);
  return clean;
}

function minWarning(fund, amount, total) {
  const min = splitOf().minimum[fund] || 0;
  if (!min || !(total > 0) || amount == null || amount * 100 >= min * total) return "";
  return `Below the suggested minimum of ${min}%`;
}

const LOCK_ICON = '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="11" width="14" height="9" rx="2"/><path class="lock-shackle" d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>';

function fundRow(id, name, amount, total, view, pctText) {
  const { suggested, minimum } = splitOf();
  const demo = state.data.mode === "demo";
  // Live keeps this week's payments, so a fund can't go below what it already paid for.
  const spent = !demo && view.ready ? state.data.opening[id] - view.fundsNow[id] : 0;
  const bad = state.error && state.errorField === id;
  const flex = FLEX_FUNDS.includes(id) ? ` <span class="chip-flex">Flexible</span>` : "";
  const min = minimum[id] ? ` · min ${minimum[id]}%` : "";
  const warn = minWarning(id, amount, total);
  const isLocked = locked.has(id);
  const off = isLocked ? " readonly" : "";
  const spentHint = spent > 0 && !bad ? `<div class="hint" id="${id}-hint">${hk(spent)} already spent: the lowest you can set</div>` : "";
  const error = bad ? `<div class="error" id="${id}-error" role="alert" data-key="ferr-${id}-${escapeHtml(state.error)}">${escapeHtml(state.error)}</div>` : "";
  const described = [`${id}-suggest`, spentHint && `${id}-hint`, bad && `${id}-error`].filter(Boolean).join(" ");
  return `<div class="budget-row${isLocked ? " is-locked" : ""}" data-fund-row="${id}">
      <div class="budget-row-top">
        <label class="budget-name" for="${id}">${name}${flex}</label>
        <span class="budget-row-tools"><span class="budget-suggest" id="${id}-suggest">Suggested ${suggested[id]}%${min}</span>
        <button type="button" class="lock-btn" data-lock="${id}" aria-pressed="${isLocked}" aria-label="Lock ${name}" title="A locked fund stays fixed while the others move">${LOCK_ICON}</button></span>
      </div>
      <div class="budget-inputs">
        <div class="pct-input"><input id="${id}-pct" data-pct="${id}" inputmode="decimal" autocomplete="off" aria-label="${name} percent of the week" value="${escapeHtml(pctText)}"${off}><span class="cur" aria-hidden="true">%</span></div>
        <div class="money-input${bad ? " invalid" : ""}"><span class="cur" aria-hidden="true">HK$</span>`
    + `<input id="${id}" data-budget="${id}" inputmode="decimal" autocomplete="off" value="${amount == null ? "" : escapeHtml(plainAmount(amount))}"${bad ? ' aria-invalid="true"' : ""} aria-describedby="${described}"${off}></div>
      </div>
      <div class="slider-wrap">
        <input type="range" class="slider fc-${id}" id="${id}-slider" data-slider="${id}" data-min="${spent > 0 ? spent : 0}" min="0" max="${fundMax(total)}" step="1" value="${Math.floor((amount || 0) / 100)}" aria-label="${name} slider" aria-valuetext="${hk(amount || 0)}"${isLocked ? " disabled" : ""}>
        <output class="slider-bubble num" data-bubble="${id}" for="${id}-slider" aria-hidden="true" hidden></output>
      </div>
      <div class="budget-warn" id="${id}-warn" aria-live="polite">${escapeHtml(warn)}</div>
      ${spentHint}${error}
    </div>`;
}

export function budgetFields(view) {
  const { amounts, total } = startValues(view);
  const texts = percentTexts(amounts, total);
  const rows = FUND_FIELDS.map(([id, name]) => fundRow(id, name, amounts[id], total, view, texts[id])).join("");
  const generalError = state.error && !FUND_FIELDS.some(([id]) => id === state.errorField) ? state.error : "";
  return `${stackHtml(amounts)}<div class="field budget-total-field">
      <label for="week-total">Money for this week</label>
      <div class="money-input big-input"><span class="cur" aria-hidden="true">HK$</span><input id="week-total" inputmode="decimal" autocomplete="off" value="${escapeHtml(plainAmount(total))}"></div>
      <input type="range" class="slider slider-total" id="week-total-slider" min="0" max="${totalMax(total)}" step="10" value="${Math.floor((total || 0) / 100)}" aria-label="Money for this week slider" aria-valuetext="${hk(total || 0)}">
    </div>
    <div class="budget-tools">
      <button class="ghost small" type="button" id="use-suggested">Use suggested split</button>
      <span class="hint">Move one fund and the others follow, always 100%. Lock a fund to keep it fixed.</span>
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

// Sets a property only when it changes: fewer style recalculations while a slider moves.
function put(el, key, value) {
  if (el && el[key] !== value) el[key] = value;
}

// Called after every change: segment widths, legend, total, and the sliders follow the amounts.
export function paintStack(skip) {
  const bar = document.getElementById("stack-bar");
  if (!bar) return;
  const clean = cleanAmounts(readAmounts());
  const all = sum(clean);
  const weekTotal = readTotal() || 0;
  const totalSlider = document.getElementById("week-total-slider");
  if (totalSlider && totalSlider !== skip) {
    put(totalSlider, "max", String(totalMax(weekTotal)));
    put(totalSlider, "value", String(Math.floor(weekTotal / 100)));
  }
  totalSlider?.setAttribute("aria-valuetext", hk(weekTotal));
  for (const fund of FUND_ORDER) {
    const seg = bar.querySelector(`[data-seg="${fund}"]`);
    if (seg) seg.style.width = all > 0 ? `${(clean[fund] * 100) / all}%` : "0%";
    put(document.querySelector(`[data-legend="${fund}"]`), "textContent", hk(clean[fund]));
    const slider = document.getElementById(`${fund}-slider`);
    if (!slider) continue;
    put(slider, "max", String(fundMax(weekTotal)));
    if (slider !== skip) put(slider, "value", String(Math.floor(clean[fund] / 100)));
    slider.setAttribute("aria-valuetext", hk(clean[fund]));
    // The filled part of the track (styles.css --fill), through the CSSOM: the CSP allows it.
    const max = Number(slider.max) || 0;
    slider.style.setProperty("--fill", `${max > 0 ? Math.min((Number(slider.value) * 100) / max, 100) : 0}%`);
  }
  bar.classList.toggle("is-empty", all === 0);
  bar.setAttribute("aria-label", stackLabel(clean));
  put(document.getElementById("stack-total"), "textContent", hk(all));
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
  const texts = percentTexts(amounts, total);
  for (const fund of FUND_ORDER) {
    const pct = document.getElementById(`${fund}-pct`);
    if (pct && pct !== skip) put(pct, "value", texts[fund]);
    put(document.getElementById(`${fund}-warn`), "textContent", minWarning(fund, amounts[fund], total));
  }
  const foot = document.getElementById("budget-foot");
  if (foot && setHtml(foot, footHtml(cleanAmounts(amounts), total))) bindFoot();
}

// Writes the amounts into the HK$ fields, except `skip` (the field being typed in).
function setAmounts(amounts, skip) {
  for (const fund of FUND_ORDER) {
    const input = document.getElementById(fund);
    if (input && input !== skip) put(input, "value", plainAmount(amounts[fund]));
  }
}

// The hard floors per fund (Live: what each already paid for this week).
function floorsOf() {
  const floors = {};
  document.querySelectorAll("[data-slider]").forEach((slider) => { floors[slider.dataset.slider] = Number(slider.dataset.min) || 0; });
  return floors;
}

// Move one fund to `cents`; the other unlocked funds follow so the six add up to the total.
// Without a total yet (HK$0), only that fund changes and the foot offers to match the total.
// `skip` is the field being typed in: left as typed unless the amount had to be clamped.
function moveFund(fund, cents, skip) {
  const total = readTotal() || 0;
  if (!(total > 0)) {
    setAmounts({ ...cleanAmounts(readAmounts()), [fund]: Math.max(cents, 0) }, skip);
    return;
  }
  const next = rebalance(cleanAmounts(readAmounts()), fund, Math.max(cents, 0), total, { floors: floorsOf(), locked });
  setAmounts(next, next[fund] === cents ? skip : null);
}

// What is kept when a slider or a field is released (debounced): a re-render shows the same
// numbers. Only Save sends them to the server (in Demo, a save restarts the demo week).
let draftTimer = 0;
function saveDraft() {
  clearTimeout(draftTimer);
  draftTimer = setTimeout(() => {
    if (!document.getElementById("week-total")) return;
    const draft = { total: document.getElementById("week-total").value };
    for (const fund of FUND_ORDER) draft[fund] = document.getElementById(fund)?.value ?? "";
    state.fundDraft = draft;
  }, DRAFT_MS);
}

// The value bubble above a slider thumb, while it is dragged or has the keyboard focus.
function showBubble(slider) {
  const bubble = document.querySelector(`[data-bubble="${slider.dataset.slider}"]`);
  if (!bubble) return;
  document.querySelectorAll("[data-bubble]").forEach((other) => { if (other !== bubble) other.hidden = true; });
  const max = Number(slider.max) || 0;
  const ratio = max > 0 ? Math.min(Number(slider.value) / max, 1) : 0;
  const amount = parseAmount(document.getElementById(slider.dataset.slider)?.value ?? "", true) || 0;
  const pct = document.getElementById(`${slider.dataset.slider}-pct`)?.value || "0";
  put(bubble, "textContent", `${hk(amount)} · ${pct}%`);
  bubble.style.left = `calc(${ratio * 100}% + ${(0.5 - ratio) * THUMB_PX}px)`;
  bubble.hidden = false;
}

function hideBubble(slider) {
  const bubble = document.querySelector(`[data-bubble="${slider.dataset.slider}"]`);
  if (bubble) bubble.hidden = true;
}

// Slider input arrives faster than the screen paints: keep the latest, apply it once per frame.
let frame = 0;
let pending = null;
function queueSlider(slider) {
  pending = slider;
  if (!frame) frame = requestAnimationFrame(applySlider);
}

function applySlider() {
  frame = 0;
  const slider = pending;
  pending = null;
  if (!slider || !slider.isConnected) return;
  moveFund(slider.dataset.slider, Number(slider.value) * 100, null);
  refresh();
  showBubble(slider);
}

function bindFoot() {
  document.getElementById("rest-to-savings")?.addEventListener("click", () => {
    const amounts = readAmounts();
    const total = readTotal() || 0;
    const others = FUND_ORDER.filter((f) => f !== "savings").reduce((acc, f) => acc + (amounts[f] || 0), 0);
    document.getElementById("savings").value = plainAmount(Math.max(total - others, 0));
    refresh();
    saveDraft();
  });
  document.getElementById("match-total")?.addEventListener("click", () => {
    const amounts = readAmounts();
    document.getElementById("week-total").value = plainAmount(FUND_ORDER.reduce((acc, f) => acc + (amounts[f] || 0), 0));
    refresh();
    saveDraft();
  });
}

// A new total keeps each fund's share: exact proportional parts (largest remainder), locked
// funds kept when they still fit.
function scaleTo(amounts, total) {
  const clean = cleanAmounts(amounts);
  const keep = FUND_ORDER.filter((f) => locked.has(f));
  const kept = keep.reduce((acc, f) => acc + clean[f], 0);
  const moving = FUND_ORDER.filter((f) => !keep.includes(f));
  if (!moving.length || kept > total) return distribute(total, clean);
  const weights = {};
  for (const f of moving) weights[f] = clean[f];
  return { ...clean, ...distribute(total - kept, weights) };
}

function toggleLock(btn) {
  const fund = btn.dataset.lock;
  if (locked.has(fund)) locked.delete(fund);
  else locked.add(fund);
  const on = locked.has(fund);
  btn.setAttribute("aria-pressed", String(on));
  btn.closest(".budget-row")?.classList.toggle("is-locked", on);
  const slider = document.getElementById(`${fund}-slider`);
  if (slider) slider.disabled = on;
  for (const id of [fund, `${fund}-pct`]) {
    const input = document.getElementById(id);
    if (input) input.readOnly = on;
  }
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
      const assignedBefore = sum(cleanAmounts(amounts));
      if (assignedBefore === lastTotal) {
        setAmounts(scaleTo(amounts, total)); // keep it at exactly 100%
      } else {
        const scaled = {};
        for (const fund of FUND_ORDER) scaled[fund] = Math.floor(((amounts[fund] || 0) * total) / lastTotal);
        setAmounts(scaled);
      }
    }
    lastTotal = total;
    refresh(skip);
  };
  totalInput.addEventListener("input", () => onTotal());
  totalInput.addEventListener("change", saveDraft);
  const totalSlider = document.getElementById("week-total-slider");
  totalSlider?.addEventListener("input", (event) => {
    totalInput.value = plainAmount(Number(event.target.value) * 100);
    onTotal(event.target);
  });
  totalSlider?.addEventListener("change", saveDraft);
  // A percent sets the fund's amount from the total; the others follow.
  document.querySelectorAll("[data-pct]").forEach((input) => {
    input.addEventListener("input", () => {
      const pct = parsePercent(input.value);
      const total = readTotal();
      if (pct == null || total == null || input.readOnly) return;
      moveFund(input.dataset.pct, Math.round((total * pct) / 100), null);
      refresh(input);
    });
    input.addEventListener("change", () => {
      refresh(); // the shown percent settles to its exact value when the field is left
      saveDraft();
    });
  });
  // An amount updates its percent; the others follow.
  document.querySelectorAll("[data-budget]").forEach((input) => {
    input.addEventListener("input", () => {
      const cents = parseAmount(input.value, true);
      if (cents != null && !input.readOnly) moveFund(input.dataset.budget, cents, input);
      refresh();
    });
    input.addEventListener("change", saveDraft);
  });
  // A slider moves its fund in HK$1 steps, from 0 to the weekly total, never below what Live
  // already spent from it; the other funds follow. Keyboard arrows work natively (HK$1 a step).
  document.querySelectorAll("[data-slider]").forEach((slider) => {
    slider.addEventListener("input", () => queueSlider(slider));
    slider.addEventListener("change", () => {
      saveDraft();
      if (document.activeElement !== slider) hideBubble(slider);
    });
    slider.addEventListener("pointerdown", () => showBubble(slider));
    slider.addEventListener("focus", () => showBubble(slider));
    slider.addEventListener("blur", () => hideBubble(slider));
    slider.addEventListener("pointerup", () => { if (document.activeElement !== slider) hideBubble(slider); });
  });
  document.querySelectorAll("[data-lock]").forEach((btn) => btn.addEventListener("click", () => toggleLock(btn)));
  paintStack();
  document.getElementById("use-suggested")?.addEventListener("click", () => {
    const total = readTotal();
    if (total == null) return;
    setAmounts(splitAmounts(total, splitOf().suggested));
    refresh();
    saveDraft();
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
