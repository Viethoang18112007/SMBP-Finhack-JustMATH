// "This week": pace warnings ("at this pace, Snacks run out around Sat") and a breakdown,
// from the server (assistant.insights, offline rules). Today shows the short version, Week the full one.

import { escapeHtml, hk } from "../format.js";
import { state } from "../store.js";

function warningHtml(warning) {
  return `<li class="ins-warn ${escapeHtml(warning.level)}"><strong>${escapeHtml(warning.title)}</strong><span>${escapeHtml(warning.text)}</span></li>`;
}

// Today: the headline and the warnings, with a link to the full analysis on Week.
export function insightsCard() {
  const ins = state.data.insights;
  if (!ins || !ins.ready) return "";
  const ok = ins.warnings.length === 0;
  return `<section class="card ins-card${ok ? " ok" : ""}" aria-labelledby="ins-title">
      <div class="card-head"><h2 class="title" id="ins-title">This week</h2><span class="ins-badge">${ok ? "On track" : "Heads up"}</span></div>
      <p class="ins-head">${escapeHtml(ins.headline)}</p>
      ${ok ? "" : `<ul class="ins-list">${warningHtml(ins.warnings[0])}</ul>`}
      <button type="button" class="ghost small" data-screen-go="week">${ins.warnings.length > 1 ? `See all ${ins.warnings.length} on Week` : "See Week"}</button>
    </section>`;
}

// Week (current week only): where the money went, the warnings and a few plain notes.
export function insightsDetail() {
  const ins = state.data.insights;
  if (!ins || !ins.ready) return "";
  const bars = ins.breakdown.map((row) => `<li><div class="ins-row"><span>${escapeHtml(row.name)}</span><span class="num">${hk(row.spent)} · ${row.share}%</span></div>
      <div class="bar thin" aria-hidden="true"><span data-bar="ins-${escapeHtml(row.fund)}" data-ratio="${row.share / 100}"></span></div></li>`).join("");
  return `<section class="card ins-card" aria-labelledby="ins-detail-title">
      <h2 class="title" id="ins-detail-title">Where the money went</h2>
      <p class="ins-head">${escapeHtml(ins.headline)}</p>
      ${ins.warnings.length ? `<ul class="ins-list">${ins.warnings.map(warningHtml).join("")}</ul>` : ""}
      ${bars ? `<div class="label">${hk(ins.total)} in ${ins.daysSoFar} ${ins.daysSoFar === 1 ? "day" : "days"}</div><ul class="ins-bars">${bars}</ul>` : `<p class="empty-line">No payments yet this week.</p>`}
      ${ins.notes.length ? `<details class="more"><summary>More notes</summary><ul class="ins-notes">${ins.notes.map((n) => `<li>${escapeHtml(n)}</li>`).join("")}</ul></details>` : ""}
    </section>`;
}
