// The 30 day projection card (server: projection.py). A plain SVG line chart:
// solid line = real cumulative spending, dashed line = projection coloured by status,
// thin grey line = budget pace. The status is always a word in a pill, never colour alone.

import { dayLabel, hk } from "../format.js";

const W = 320;

function points(values, x0, xStep, yScale, h) {
  return values.map((v, i) => `${(x0 + i * xStep).toFixed(1)},${(h - v * yScale).toFixed(1)}`).join(" ");
}

// `zero` (cooked.py): the first day ahead where the projection passes the budget line, or null.
export function projectionCard(proj, big = false, zero = undefined) {
  const id = big ? "projection-week" : "projection-card";
  const title = `<h2 class="title" id="${id}-title">Next 30 days</h2>`;
  if (!proj || !proj.ready) {
    const why = proj && proj.reason === "no_budget"
      ? "Set a weekly budget first. The projection starts after 2 days of use."
      : "Projection starts after 2 days of use.";
    return `<section class="card projection" id="${id}" aria-labelledby="${id}-title">${title}<p class="sub">${why}</p></section>`;
  }
  const h = big ? 180 : 120;
  const real = proj.real.map((r) => r.cents);
  const ahead = [real[real.length - 1], ...proj.projected.map((p) => p.cents)];
  const total = real.length + proj.projected.length; // days on the x axis
  const paceLine = [proj.pace, proj.pace * total];
  const top = Math.max(ahead[ahead.length - 1], paceLine[1], 1) * 1.08;
  const yScale = (h - 6) / top;
  const xStep = W / (total - 1);
  const realPts = points(real, 0, xStep, yScale, h);
  const aheadPts = points(ahead, (real.length - 1) * xStep, xStep, yScale, h);
  const pacePts = `0,${(h - paceLine[0] * yScale).toFixed(1)} ${W},${(h - paceLine[1] * yScale).toFixed(1)}`;
  const todayX = ((real.length - 1) * xStep).toFixed(1);
  // The zero point: where the projection passes the budget pace (cooked.zero_day).
  let zeroMark = "";
  let zeroLine = "";
  if (zero) {
    const zx = ((real.length - 1 + zero.day) * xStep).toFixed(1);
    const zy = (h - ahead[zero.day] * yScale).toFixed(1);
    zeroMark = `<line class="proj-zero-line" x1="${zx}" y1="0" x2="${zx}" y2="${h}"/><circle class="proj-zero" cx="${zx}" cy="${zy}" r="5"/>`;
    zeroLine = `<p class="proj-zero-text"><span class="proj-zero-dot" aria-hidden="true"></span>HK$0 around ${dayLabel(zero.date)} at this pace.</p>`;
  } else if (zero === null) {
    zeroLine = `<p class="proj-zero-text ok">No HK$0 day in the next 30 days.</p>`;
  }
  const label = `Chart: real spending ${hk(real[real.length - 1])} so far; at your pace ${hk(proj.projected30)} in the next 30 days, against a budget of ${hk(proj.budget30)}. Status: ${proj.label}.`;
  return `<section class="card projection${big ? " big" : ""}" id="${id}" aria-labelledby="${id}-title">
      <div class="card-head">${title}<span class="pill status-${proj.status}">${proj.label}</span></div>
      <svg class="proj-chart status-${proj.status}" viewBox="0 0 ${W} ${h}" preserveAspectRatio="none" role="img" aria-label="${label}">
        <line class="proj-today" x1="${todayX}" y1="0" x2="${todayX}" y2="${h}"/>
        <polyline class="proj-pace" points="${pacePts}"/>
        <polyline class="proj-real" pathLength="1" points="${realPts}"/>
        <polyline class="proj-ahead" points="${aheadPts}"/>
        ${zeroMark}
      </svg>
      <ul class="proj-legend">
        <li><span class="key real" aria-hidden="true"></span>Real</li>
        <li><span class="key ahead status-${proj.status}" aria-hidden="true"></span>Projection</li>
        <li><span class="key pace" aria-hidden="true"></span>Budget pace</li>
      </ul>
      ${zeroLine}
      <details class="more proj-more"><summary>Numbers</summary>
        <p class="proj-line">At this pace: <strong class="num">${hk(proj.projected30)}</strong> in 30 days · Budget: <strong class="num">${hk(proj.budget30)}</strong></p>
        <p class="hint">From your last ${proj.window} ${proj.window === 1 ? "day" : "days"}. Savings not counted.</p>
      </details>
    </section>`;
}
