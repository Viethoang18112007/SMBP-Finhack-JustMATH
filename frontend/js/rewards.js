// Rewards for good money habits, drawn from state.data.rewards (rewards.py on the server):
// the logging streak and its shape, last week's stars, badges and campus medals.
// SVG colours come from CSS classes (the CSP blocks inline style attributes).

import { escapeHtml, hk } from "./format.js";
import { state } from "./store.js";

// One shape per streak level: square, star, diamond, hexagon, crown.
const SHAPES = {
  square: '<rect x="4" y="4" width="16" height="16" rx="3.5"/>',
  star: '<path d="M12 2.6l2.9 5.9 6.5.9-4.7 4.6 1.1 6.4L12 17.4l-5.8 3 1.1-6.4-4.7-4.6 6.5-.9z"/>',
  diamond: '<path d="M12 2.4 21.6 12 12 21.6 2.4 12z"/>',
  hexagon: '<path d="M12 2.4l8.3 4.8v9.6L12 21.6l-8.3-4.8V7.2z"/>',
  crown: '<path d="M3 19h18l-1.4-11-4.7 4.3L12 5l-2.9 7.3L4.4 8z"/>',
};
const NO_SHAPE = '<circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="3 3"/>';

export function shapeSvg(shape, size = 28) {
  const body = SHAPES[shape] || NO_SHAPE;
  return `<svg class="shape shape-${escapeHtml(shape || "none")}" viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true" fill="currentColor">${body}</svg>`;
}

function days(n) {
  return `${n} ${n === 1 ? "day" : "days"}`;
}

// "3 day streak" with its shape, and what comes next.
export function streakChip(streak, withNext = true) {
  if (!streak) return "";
  const label = streak.days ? `${days(streak.days)} in a row` : "No streak yet";
  const next = withNext && streak.next
    ? `<span class="streak-next">${escapeHtml(streak.next.name)} in ${days(streak.next.daysToGo)}</span>`
    : "";
  const hint = streak.days && !streak.loggedToday ? `<span class="streak-next">Log today to keep it</span>` : next;
  const title = streak.days ? `${streak.name} streak: ${label}` : "Log a payment to start a streak";
  return `<span class="streak-chip" role="img" aria-label="${escapeHtml(title)}">${shapeSvg(streak.shape)}`
    + `<span class="streak-text"><strong>${escapeHtml(label)}</strong>${hint}</span></span>`;
}

const STAR = '<path d="M12 2.6l2.9 5.9 6.5.9-4.7 4.6 1.1 6.4L12 17.4l-5.8 3 1.1-6.4-4.7-4.6 6.5-.9z"/>';

export function starsHtml(count) {
  const stars = [1, 2, 3, 4, 5].map((n) =>
    `<svg class="star${n <= count ? " on" : ""}" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="currentColor">${STAR}</svg>`
  ).join("");
  return `<span class="stars" role="img" aria-label="${count} of 5 stars">${stars}</span>`;
}

// Today: one compact row (streak and last week's stars), a tap away from the full card on Week.
export function rewardsStrip() {
  const rewards = state.data.rewards;
  if (!rewards) return "";
  const last = rewards.lastWeek;
  const stars = last ? `<span class="strip-stars">Last week ${starsHtml(last.stars)}</span>` : "";
  return `<button type="button" class="card rewards-strip" data-screen-go="week" aria-label="Your progress, on the Week screen">`
    + `${streakChip(rewards.streak, false)}${stars}</button>`;
}

const MEDAL = '<circle cx="12" cy="14" r="6.5"/><path d="M8.5 2.5h3l1.5 5h-3zM15.5 2.5h-3l-1 3.4 1.3 1.6z" opacity="0.65"/>';

function medalSvg(medal) {
  return `<svg class="medal medal-${medal || "none"}" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="currentColor">${MEDAL}</svg>`;
}

const MEDAL_NAME = { bronze: "Bronze", silver: "Silver", gold: "Gold" };

function placesText(n) {
  return `${n} ${n === 1 ? "place" : "places"}`;
}

// Map: the medal for the campus shown. It counts places where a logged meal fit that day's money.
export function medalLine() {
  const rewards = state.data.rewards;
  if (!rewards) return "";
  const row = rewards.medals.find((m) => m.campus === state.data.campus);
  if (!row) return "";
  const now = row.medal ? `${MEDAL_NAME[row.medal]} medal` : "No medal yet";
  const next = row.next ? ` ${MEDAL_NAME[row.next.medal]} at ${placesText(row.next.at)}.` : " Top medal.";
  return `<p class="medal-line">${medalSvg(row.medal)}<span><strong>${escapeHtml(now)} near ${escapeHtml(row.name)}</strong>`
    + ` ${placesText(row.count)} tried within budget.${next} Tap a place, then "Log a meal here".</span></p>`;
}

function badgeIcon(earned) {
  const path = earned
    ? '<circle cx="12" cy="12" r="9"/><path d="m8 12.5 2.6 2.6L16 9.6" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
    : '<circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="2"/><rect x="9" y="11" width="6" height="5" rx="1"/><path d="M10 11V9.5a2 2 0 0 1 4 0V11" fill="none" stroke="currentColor" stroke-width="1.6"/>';
  return `<svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true" fill="currentColor">${path}</svg>`;
}

function badgesGrid(badges) {
  const earned = badges.filter((b) => b.earned).length;
  const items = badges.map((badge) =>
    `<li class="badge-item${badge.earned ? " earned" : ""}">${badgeIcon(badge.earned)}`
    + `<span class="badge-name">${escapeHtml(badge.name)}</span><span class="badge-how">${escapeHtml(badge.how)}</span>`
    + `<span class="sr-only">${badge.earned ? "Earned" : "Not earned yet"}</span></li>`
  ).join("");
  return `<div class="label">Badges <span class="opt">${earned} of ${badges.length}</span></div><ul class="badges">${items}</ul>`;
}

// Week (current week): last week's stars, the streak and the badges.
export function progressCard() {
  const rewards = state.data.rewards;
  if (!rewards) return "";
  const last = rewards.lastWeek;
  const week = last
    ? `<div class="progress-row">${starsHtml(last.stars)}<span><strong>Last week: ${last.stars} of 5</strong> ${escapeHtml(last.why)} `
      + `${last.left > 0 ? `${hk(last.left)} of ${hk(last.budget)} left.` : ""}</span></div>`
    : `<p class="sub">Stars for your week show up once a full week with a budget has ended. 3 stars means money was left.</p>`;
  const streak = rewards.streak;
  const best = streak.best > streak.days ? ` Best so far: ${days(streak.best)}.` : "";
  return `<section class="card progress-card" aria-labelledby="progress-title">
      <h2 class="title" id="progress-title">Your progress</h2>
      ${week}
      <div class="progress-row">${streakChip(streak)}</div>
      <p class="hint">A payment logged every day keeps the streak. Its shape changes at 3, 7, 14 and 30 days.${best}</p>
      ${badgesGrid(rewards.badges)}
    </section>`;
}
