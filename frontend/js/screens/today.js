import { FLEX_FUNDS, FUND_NAME, dayLabel, escapeHtml, hk } from "../format.js";
import { paymentsOn, state } from "../store.js";
import { paymentRow, screenError } from "./rows.js";
import { budgetFields } from "./settings.js";
import { cookedCard } from "./cooked.js";
import { projectionCard } from "./projection.js";
import { tanksHtml } from "./tanks.js";
import { reviewCard } from "../inbox.js";
import { insightsCard } from "./insights.js";
import { rewardsStrip } from "../rewards.js";
import { NATIVE } from "../config.js";

const FUND_ORDER = ["main", "snack", "fixed", "experience", "development", "savings"];
// The fund bar colour follows the tank tone: amber from 50% down, red under 20%.
const BAR_TONE = { mid: "near", low: "over", empty: "over", neutral: "neutral" };

// Under Long-term Savings: what the weeks that ended have added, flexible leftovers included.
function savingsExtra() {
  const pot = state.data.savingsPot;
  if (!pot || pot.total <= 0) return "";
  const flex = pot.lastFlexMoved > 0 ? ` (${hk(pot.lastFlexMoved)} moved from flexible funds last week)` : "";
  return `<div class="fund-sub">+ ${hk(pot.total)} saved from past weeks${flex}</div>`;
}

// The five funds plus savings: what is left of the week's amount, with a thin bar each.
function fundList(view) {
  const tanks = new Map((state.data.tanks || []).map((tank) => [tank.fund, tank]));
  return FUND_ORDER.map((fund) => {
    const left = view.fundsNow[fund];
    const tank = tanks.get(fund);
    const week = tank ? tank.allocation : state.data.opening[fund];
    const ratio = tank && week > 0 ? tank.level / 10000 : 0;
    const tone = tank ? BAR_TONE[tank.tone] || "" : "";
    const empty = left <= 0 ? " empty" : "";
    const flex = FLEX_FUNDS.includes(fund) ? `<span class="chip-flex">Flexible</span>` : "";
    const extra = fund === "savings" ? savingsExtra() : "";
    return `<li class="fund${empty}">
        <div class="fund-top"><span class="fund-left"><span class="fund-name">${FUND_NAME[fund]}</span><span class="fund-meta">${flex}</span></span>
          <span class="fund-amt"><strong class="num" data-count="fund-${fund}" data-cents="${left}">${hk(left)}</strong><span class="of num"><span class="sr-only"> left of</span> / ${hk(week)}</span></span></div>
        <div class="bar thin" aria-hidden="true"><span data-bar="fund-${fund}" data-ratio="${ratio}" data-tone="${tone}"></span></div>
        ${extra}
      </li>`;
  }).join("");
}

// What the flexible funds do, and what they will hand to Long-term Savings on Sunday: one tap away.
function flexNote(view) {
  const left = view.flexLeft || 0;
  const end = left > 0
    ? `What is left in them on Sunday (${hk(left)} now) moves to Long-term Savings.`
    : "Nothing is left in them to move to Long-term Savings this week.";
  return `<details class="more flex-more"><summary>What are flexible funds?</summary><p class="flex-note">Experience and Development can cover a food day that runs out. ${end}</p></details>`;
}

// List (the default) or Tanks: two views of the same six balances.
function viewToggle() {
  const tanks = state.fundView === "tanks";
  return `<div class="seg small" role="group" aria-label="Show the funds as">`
    + `<button type="button" class="${tanks ? "" : "on"}" data-fund-view="list" aria-pressed="${!tanks}">List</button>`
    + `<button type="button" class="${tanks ? "on" : ""}" data-fund-view="tanks" aria-pressed="${tanks}">Tanks</button></div>`;
}

// Before a budget is saved: HK$0 left today, never a made-up amount.
function zeroHero(view) {
  return `<section class="card hero" aria-labelledby="left-label">
      <div class="hero-top"><span class="kicker">${escapeHtml(dayLabel(state.data.today))}</span><span class="kicker">${view.daysLeft} ${view.daysLeft === 1 ? "day" : "days"} left</span></div>
      <div class="hero-label" id="left-label">Left to spend today</div>
      <div class="big num" aria-describedby="left-label">${hk(0)}</div>
      <p class="hero-sub">Set your weekly budget below to start.</p>
    </section>`;
}

// No budget yet (first launch, or a new live week): Today is the setup, one button to start.
function setupCard(view) {
  const fresh = state.data.weeks.length === 0;
  const title = fresh ? "Set your weekly budget" : "New week: set your budget";
  let sub = state.data.mode === "demo"
    ? "We filled in a suggested split. Change the total, or any fund in % or HK$, until it fits your week."
    : "Every fund starts at HK$0. Slide or type each one; the total adds up as you go.";
  if (state.data.prefill) sub = "Last week's amounts are filled in. Check them, then start.";
  return `${screenError()}${zeroHero(view)}<section class="card setup" aria-labelledby="setup-title">
      <div class="kicker">${escapeHtml(dayLabel(state.data.today))} · ${view.daysLeft} ${view.daysLeft === 1 ? "day" : "days"} left this week</div>
      <h2 class="title" id="setup-title">${title}</h2>
      <p class="sub">${sub}</p>
      ${budgetFields(view)}
      <button class="primary" id="apply" type="button">Start my week</button>
    </section>`;
}

// The web demo's extra cards. The iPhone app keeps Today to the basics: what is left today, scan,
// what waits for review, the funds and today's payments (the analysis stays on Week).
function extraCards() {
  return `${cookedCard(state.data.cooked)}
    ${projectionCard(state.data.projection, false, state.data.cooked && state.data.cooked.ready ? state.data.cooked.zero : undefined)}
    ${insightsCard()}`;
}

export function todayScreen(view) {
  if (!view.ready) return setupCard(view);
  const items = paymentsOn(state.data.today);
  const left = view.todayRemaining;
  const over = left < 0;
  // A zero budget with nothing spent is not "over": the bar stays empty and neutral.
  const zero = view.allowance === 0 && view.spentToday === 0;
  const ratio = view.allowance > 0 ? Math.min(view.spentToday / view.allowance, 1) : zero ? 0 : 1;
  const tone = zero ? "" : view.overToday ? "over" : view.notice ? "near" : "";
  const days = `${view.daysLeft} ${view.daysLeft === 1 ? "day" : "days"}`;
  const notice = state.showNotice && view.notice
    ? `<div class="notice warn" role="status">${hk(view.spentToday)} of today's ${hk(view.allowance)} used.</div>`
    : "";
  const overLine = over ? `<div class="over-by">${hk(-left)} over today's budget. Tomorrow already includes it.</div>` : "";
  // render() sets the bar fill through element.style (motion.js): the CSP blocks inline style attributes.
  return `${screenError()}${notice}
    <section class="card hero" aria-labelledby="left-label">
      <div class="hero-top"><span class="kicker">${escapeHtml(dayLabel(state.data.today))}</span><span class="kicker">${days} left</span></div>
      <div class="hero-label" id="left-label">Left to spend today</div>
      <div class="big num${over ? " is-over" : ""}" aria-describedby="left-label" data-count="left" data-cents="${Math.max(left, 0)}">${hk(Math.max(left, 0))}</div>
      ${overLine}
      <div class="bar" aria-hidden="true"><span data-bar="today" data-ratio="${ratio}" data-tone="${tone}"></span></div>
      <div class="hero-foot"><span>Spent <strong class="num" data-count="spent" data-cents="${view.spentToday}">${hk(view.spentToday)}</strong> of ${hk(view.allowance)}</span><span>Tomorrow <strong class="num">${hk(view.tomorrow)}</strong></span></div>
    </section>
    <button type="button" class="ghost scan-today" data-scan-today>
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2"/><path d="M8 9h8M8 12h8M8 15h5"/></svg>
      Scan a receipt
    </button>
    ${rewardsStrip()}
    ${reviewCard()}
    ${NATIVE ? "" : extraCards()}
    <section class="card" id="funds-card" aria-labelledby="funds-label">
      <div class="card-head"><h2 class="title" id="funds-label">Funds this week</h2>${NATIVE ? "" : viewToggle()}</div>
      ${state.fundView === "tanks" && !NATIVE ? tanksHtml(state.data.tanks) : `<ul class="funds">${fundList(view)}</ul>`}
      ${NATIVE ? "" : flexNote(view)}
    </section>
    <section class="card" aria-labelledby="pays-label">
      <h2 class="title" id="pays-label">Today's payments</h2>
      <div class="list">${items.length ? items.slice().reverse().map((p) => paymentRow(p, { confirming: state.undoId })).join("") : `<p class="empty-line">Nothing yet today.</p>`}</div>
    </section>`;
}
