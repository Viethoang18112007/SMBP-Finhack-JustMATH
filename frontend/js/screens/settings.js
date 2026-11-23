import { budgetFields } from "../budget.js";
import { state } from "../store.js";
import { connectedCard, tapButtons } from "../inbox.js";

export { budgetFields };

export function settingsScreen(view) {
  const demo = state.data.mode === "demo";
  const prefill = !view.ready && state.data.prefill;
  const effect = demo ? "Saving starts a fresh demo week." : "Payments stay.";
  const live = !demo;
  const modeCard = `<section class="card" aria-labelledby="mode-title">
      <h2 class="title" id="mode-title">Mode</h2>
      <div class="seg mode-switch" role="group" aria-label="Mode">
        <button type="button" data-switch="live" class="${live ? "on" : ""}" aria-pressed="${live}">Live</button>
        <button type="button" data-switch="demo" class="${demo ? "on" : ""}" aria-pressed="${demo}">Demo</button>
      </div>
      <p class="sub">${demo ? "Sample data on a fixed date." : "Your own data, saved on this computer."}</p>
    </section>`;
  // Each button sends {"mode": "demo", "scenario": ...} and reloads that demo week.
  const demoWeeks = demo
    ? `<div class="label">Demo weeks</div><div class="stack">
      <button class="ghost" data-scenario="sample" type="button">Sample week</button>
      <button class="ghost" data-scenario="empty" type="button">Empty week</button>
      <button class="ghost" data-scenario="over" type="button">Week already over</button>
      <button class="ghost" data-scenario="cooked" type="button">Cooked week</button>
    </div>`
    : "";
  // Guided works everywhere (it only shows screens). Auto-play saves payments, so DEMO only.
  const play = demo
    ? `<button class="ghost" type="button" data-tour="auto">Play the demo (about 2 minutes)</button>`
    : `<button class="ghost" type="button" data-tour="auto" disabled aria-describedby="autoplay-why">Play the demo</button>
      <p class="hint" id="autoplay-why">The demo plays in Demo mode only, so it never touches your data.</p>`;
  const tips = demo ? `<button class="ghost" type="button" id="reset-tips">Show the welcome tip again</button>` : "";
  const help = `<details class="card help fold">
      <summary><span class="title">Demo &amp; help</span></summary>
      <div class="stack mt-12">
        <button class="ghost" type="button" data-tour="guided">Take the tour</button>
        ${play}
        ${tips}
      </div>
      <div class="mt-12"><div class="label">Simulate a tap</div>${tapButtons("help")}</div>
      ${demoWeeks ? `<div class="mt-12">${demoWeeks}</div>` : ""}
    </details>`;
  const phone = state.phoneView;
  const display = `<details class="card fold">
      <summary><span class="title" id="display-title">Display</span></summary>
      <button type="button" class="toggle switch-row" data-phone-view aria-pressed="${phone}">
        <span>Phone view</span><span class="switch" aria-hidden="true"></span>
      </button>
      <p class="hint">Wide screens only: the app inside a simulated phone.</p>
    </details>`;
  return `<section class="card" aria-labelledby="budget-title">
      <h2 class="title" id="budget-title">Weekly budget</h2>
      <p class="sub">${prefill ? "Last week's amounts are filled in. Check them, then save." : effect}</p>
      ${budgetFields(view)}
      <button class="primary" id="apply" type="button">Save weekly budget</button>
    </section>
    ${modeCard}
    ${connectedCard()}
    ${display}
    ${help}`;
}
