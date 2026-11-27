// The SSUST widgets on the simulated home screen. They read the same state as the app (the
// numbers come from the same fields as Today), and device.renderHome draws them again after
// every render: a save, an undo, a budget change, an inbox change, a new day.
// Tapping one opens the app on Today, or on the review card when payments wait for review.

import { FUND_NAME, FUND_ORDER, escapeHtml, hk } from "./format.js";

// The same number as Today's "Left to spend today" (0 before a budget is saved).
export function leftToday(view) {
  return view && view.ready ? Math.max(view.todayRemaining, 0) : 0;
}

function pill(proj) {
  if (!proj || !proj.ready) return `<span class="pill w-pill">No projection yet</span>`;
  return `<span class="pill w-pill status-${proj.status}">${proj.label}</span>`;
}

function fundBars(data) {
  const tanks = new Map((data.tanks || []).map((t) => [t.fund, t]));
  return FUND_ORDER.map((fund) => {
    const tank = tanks.get(fund);
    const left = data.view.ready ? data.view.fundsNow[fund] : 0;
    const level = tank ? tank.level / 100 : 0;
    return `<span class="w-fund"><span class="w-fund-name">${FUND_NAME[fund]}</span><span class="w-bar fc-${fund}"><span data-w-level="${level}"></span></span><span class="num w-fund-amt">${hk(Math.max(left, 0))}</span></span>`;
  }).join("");
}

// No budget yet (a fresh live database, or a new week): HK$0 everywhere would look broken, so
// the widgets say what to do. One tap opens the setup on Today; in live mode the demo week is
// one more tap away (the same data-switch buttons as Settings, handled in main.js).
function setupWidgetsHtml(data) {
  const demo = data.mode === "live"
    ? `<button type="button" class="w-btn ghost" data-switch="demo">Try the demo week</button>`
    : "";
  return `<button type="button" class="widget small setup" data-open-app="today" aria-label="UniVault: no budget yet. Open the app to set your weekly budget">
      <span class="w-app">UniVault</span>
      <span class="w-label">Left today</span>
      <strong class="w-big w-none">No budget yet</strong>
      <span class="pill w-pill">Tap to set it</span>
    </button>
    <div class="widget medium setup" role="group" aria-label="UniVault funds: no budget yet">
      <span class="w-app">UniVault · Funds this week</span>
      <span class="w-setup-text">Set your weekly budget and these bars fill with what is left in each fund.</span>
      <span class="w-row w-actions"><button type="button" class="w-btn" data-open-app="today">Set my budget</button>${demo}</span>
    </div>`;
}

export function widgetsHtml(state, updated) {
  const data = state.data;
  if (!data || !data.view) return "";
  if (!data.view.ready) return setupWidgetsHtml(data);
  const left = hk(leftToday(data.view));
  const proj = data.projection;
  const review = (data.inbox || []).length;
  const target = review ? "review" : "today";
  const reviewLine = review ? `<span class="w-review">${review} to review</span>` : "";
  const status = proj && proj.ready ? `, ${proj.label}` : "";
  return `<button type="button" class="widget small" data-open-app="${target}" aria-label="UniVault: ${left} left today${escapeHtml(status)}. Open the app">
      <span class="w-app">UniVault</span>
      <span class="w-label">Left today</span>
      <strong class="w-big num" data-w="left">${left}</strong>
      ${pill(proj)}
    </button>
    <button type="button" class="widget medium" data-open-app="${target}" aria-label="UniVault funds: ${left} left today${review ? `, ${review} to review` : ""}. Open the app">
      <span class="w-row"><span class="w-app">UniVault · Funds this week</span>${reviewLine}</span>
      <span class="w-funds">${fundBars(data)}</span>
      <span class="w-foot">Updated ${escapeHtml(updated)}</span>
    </button>`;
}
