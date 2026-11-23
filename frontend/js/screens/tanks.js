// Fund tanks: each fund as a glass column of water. The level is what is left divided by the
// week's amount (server: money.fund_tanks, integer basis points). The visual is a bonus: the
// name, what is left, the week's amount and the percent are always written under it.

import { escapeHtml, hk } from "../format.js";

const STATE_WORD = { low: "Low", empty: "Empty", none: "Not set" };

function percentText(tank) {
  if (tank.tone === "none") return "Not set";
  const word = STATE_WORD[tank.tone];
  return word ? `${tank.percent}% · ${word}` : `${tank.percent}%`;
}

// The same information as the text, for screen readers: colour is never the only signal.
export function tankLabel(tank) {
  if (tank.tone === "none") return `${tank.name}: nothing set this week`;
  const word = STATE_WORD[tank.tone];
  return `${tank.name}: ${hk(tank.remaining)} left of ${hk(tank.allocation)}, ${tank.percent} percent${word ? `, ${word.toLowerCase()}` : ""}`;
}

function tankHtml(tank) {
  const fund = escapeHtml(tank.fund);
  const dry = tank.level <= 0 ? " is-dry" : "";
  return `<li class="tank tone-${escapeHtml(tank.tone)}${dry}">
      <span class="tank-pct num" aria-hidden="true">${escapeHtml(percentText(tank))}</span>
      <span class="tank-glass" role="img" aria-label="${escapeHtml(tankLabel(tank))}">
        <span class="tank-water" data-tank="${fund}" data-level="${tank.level}" data-allocation="${tank.allocation}"></span>
      </span>
      <span class="tank-name">${escapeHtml(tank.name)}</span>
      <span class="tank-left num" data-count="tank-${fund}" data-cents="${tank.remaining}">${hk(tank.remaining)}</span>
      <span class="tank-of num">of ${hk(tank.allocation)}</span>
    </li>`;
}

export function tanksHtml(tanks) {
  if (!tanks || !tanks.length) return `<p class="empty-line">Set your weekly budget to see the tanks.</p>`;
  return `<ul class="tanks">${tanks.map(tankHtml).join("")}</ul>
    <p class="tank-note">Water level: what is left of this week's amount.</p>`;
}
