import { dayLabel, dayMonth, escapeHtml, hk, shortDate } from "../format.js";
import { shownWeek, state, sumOn } from "../store.js";
import { screenError } from "./rows.js";
import { insightsDetail } from "./insights.js";
import { progressCard } from "../rewards.js";

// Previous and next stored weeks around the one shown. Never a week after the current one.
function neighbours(week) {
  const weeks = state.data.weeks.filter((w) => w <= state.data.weekStart);
  const before = weeks.filter((w) => w < week);
  const after = weeks.filter((w) => w > week);
  return {
    prev: before.length ? before[before.length - 1] : null,
    next: week < state.data.weekStart ? (after[0] || state.data.weekStart) : null,
  };
}

function arrow(target, label, path) {
  const icon = `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="${path}"/></svg>`;
  return target
    ? `<button class="icon-btn" type="button" data-week="${target}" aria-label="${label}">${icon}</button>`
    : `<button class="icon-btn" type="button" disabled aria-label="${label} (none)">${icon}</button>`;
}

// One line: what the week has used so far, all payments and food on its own.
function weekSummary(shown) {
  const view = shown.view;
  if (!view.ready) return `<p class="week-summary">No budget set for this week.</p>`;
  const spent = shown.payments.reduce((acc, p) => acc + p.amount, 0);
  const foodBudget = shown.opening.main + shown.opening.snack;
  const foodUsed = foodBudget - view.fundsNow.main - view.fundsNow.snack;
  const line = `<p class="week-summary">Spent ${hk(spent)} · Food ${hk(foodUsed)} of ${hk(foodBudget)}</p>`;
  // A week that has ended: its flexible leftovers went to Long-term Savings.
  const closed = shown.closed;
  if (!closed) return line;
  const moved = closed.flexMoved > 0
    ? `${hk(closed.flexMoved)} left in flexible funds moved to Long-term Savings.`
    : "Nothing was left in flexible funds to move.";
  return `${line}<p class="week-closed">${moved} Saved this week: ${hk(closed.total)}.</p>`;
}

// Only today has a budget of its own, so only today gets a colour, and its label says why.
function todayState(view) {
  if (view.overToday) return ["over", "Today · over budget"];
  if (view.notice) return ["near", "Today · near the limit"];
  return ["under", "Today · on track"];
}

export function weekScreen() {
  const shown = shownWeek();
  const view = shown.view;
  const today = state.data.today;
  const past = shown !== state.data;
  const { prev, next } = neighbours(shown.weekStart);
  const rows = view.dates.map((date) => {
    const spent = sumOn(date, shown);
    let tone = "";
    let mark = "";
    if (date === today) [tone, mark] = todayState(view);
    else if (date > today) [tone, mark] = ["ahead", "Ahead"];
    return `<div class="row" data-key="d-${date}"><button class="day ${tone}${date === today ? " today" : ""}" type="button" data-day="${date}">
      <span class="day-name"><strong>${escapeHtml(dayLabel(date))}</strong>${mark ? `<span class="tag">${mark}</span>` : ""}</span>
      <span class="num${spent ? "" : " muted"}">${spent ? hk(spent) : "-"}</span>
    </button></div>`;
  }).join("");
  const title = past ? "Past week" : "This week";
  const range = `${dayMonth(view.dates[0])} to ${shortDate(view.dates[6])}`;
  return `${screenError()}<section class="card week-head" aria-labelledby="week-title">
      <div class="week-top">
        ${arrow(prev, "Previous week", "M15 5l-7 7 7 7")}
        <div class="week-title"><h2 class="title" id="week-title">${title}${past ? ` <span class="readonly">Read only</span>` : ""}</h2><div class="sub">${escapeHtml(range)}</div></div>
        ${arrow(next, "Next week", "M9 5l7 7-7 7")}
      </div>
      ${weekSummary(shown)}
    </section>
    ${past ? "" : insightsDetail()}
    <div class="list">${rows}</div>
    ${past ? "" : progressCard()}`;
}
