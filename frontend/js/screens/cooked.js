// "How cooked are you": a gauge with the score (0 to 100) and its level in words, from the server
// (cooked.py: three factors, integer rules, not AI). A tap shows the three factors and their points,
// so anyone can check the score by hand.

import { escapeHtml } from "../format.js";
import { state } from "../store.js";

// A half circle from left to right; the coloured arc covers score / 100 of it (pathLength="100").
const ARC = "M 20 110 A 90 90 0 0 1 200 110";

export function cookedCard(c) {
  if (!c || !c.ready) return "";
  const open = Boolean(state.cookedOpen);
  const factors = c.factors.map((f) => `<li class="cooked-factor">
      <div class="cooked-factor-top"><span>${escapeHtml(f.name)}</span><strong class="num">${f.points} / ${f.max}</strong></div>
      <p class="hint">${escapeHtml(f.detail)}</p>
    </li>`).join("");
  return `<section class="card cooked level-${c.level}" id="cooked-card" aria-labelledby="cooked-title">
      <div class="card-head"><h2 class="title" id="cooked-title">How cooked are you?</h2><span class="pill level-${c.level}">${escapeHtml(c.label)}</span></div>
      <button type="button" class="cooked-gauge-btn" data-cooked-toggle aria-expanded="${open}" aria-controls="cooked-factors"
        aria-label="Cooked score ${c.score} out of 100: ${escapeHtml(c.label)}. Show the three factors">
        <svg class="cooked-gauge level-${c.level}" viewBox="0 0 220 124" role="img" aria-hidden="true">
          <path class="cooked-track" d="${ARC}" pathLength="100"/>
          <path class="cooked-value" d="${ARC}" pathLength="100" stroke-dasharray="${c.score} 100"/>
          <text class="cooked-score" x="110" y="96" text-anchor="middle">${c.score}</text>
          <text class="cooked-of" x="110" y="118" text-anchor="middle">out of 100</text>
        </svg>
        <span class="cooked-tap">${open ? "Hide why" : "Why? 3 factors"}</span>
      </button>
      <ul class="cooked-factors" id="cooked-factors"${open ? "" : " hidden"}>${factors}
        <li class="hint">The three added up. Plain rules, not AI.</li></ul>
    </section>`;
}
