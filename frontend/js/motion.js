// Motion helpers. Pure functions first (no DOM), then small DOM helpers used by render().
//
// render() replaces the screen's HTML on every change, so CSS transitions alone never fire:
// these helpers decide what is new (a screen, a row, a number) and add the classes or the
// short animations for it. Every duration comes from the tokens in styles.css (:root), and
// prefers-reduced-motion turns all of it off.

export const TAB_ORDER = ["today", "map", "week", "settings"];
const PARENT = { add: "today", day: "week" };

// The entrance class for a screen change: along the tab order (forward or back), or a
// fade-up for a sub-screen (Add from Today, Day from Week). null when nothing changed.
export function screenEnterClass(from, to) {
  if (!from || from === to) return null;
  if (PARENT[to] === from || PARENT[from] === to) return "enter-up";
  const a = TAB_ORDER.indexOf(PARENT[from] || from);
  const b = TAB_ORDER.indexOf(PARENT[to] || to);
  if (a < 0 || b < 0 || a === b) return "enter-up";
  return b > a ? "enter-fwd" : "enter-back";
}

export function prefersReducedMotion() {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch (err) {
    return false;
  }
}

// A duration token ("220ms", "0.01ms", "0.3s") in milliseconds.
export function tokenMs(name, fallback) {
  try {
    const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const value = parseFloat(raw);
    if (Number.isNaN(value)) return fallback;
    return raw.endsWith("ms") ? value : value * 1000;
  } catch (err) {
    return fallback;
  }
}

const ENTER_CLASSES = ["enter-fwd", "enter-back", "enter-up"];

// Play the screen entrance on `root` (the #screen element), restarting it if needed.
export function enterScreen(root, cls) {
  root.classList.remove(...ENTER_CLASSES);
  if (!cls || prefersReducedMotion()) return;
  void root.offsetWidth; // restart the animation
  root.classList.add(cls);
  const done = (event) => {
    if (event.target !== root) return;
    root.classList.remove(cls);
    root.removeEventListener("animationend", done);
  };
  root.addEventListener("animationend", done);
}

// The reallocation modal. Opening plays once (closed -> open), never on a re-render.
// Closing keeps the old content on screen, inert and click-through, for the exit animation,
// then removes it. Nothing waits for it: state.sheet is already null, so Escape and the
// confirm guard behave exactly as before.
let closeTimer = null;

export function cancelSheetClose(sheet) {
  if (closeTimer) clearTimeout(closeTimer);
  closeTimer = null;
  sheet.classList.remove("is-closing");
  sheet.inert = false;
}

export function openSheetAnimated(sheet) {
  if (prefersReducedMotion()) return;
  sheet.classList.remove("is-opening");
  void sheet.offsetWidth;
  sheet.classList.add("is-opening");
  // A timer, not animationend: a re-render may replace the panel while it is opening.
  setTimeout(() => sheet.classList.remove("is-opening"), tokenMs("--dur-slow", 360) + 40);
}

export function isSheetClosing(sheet) {
  return sheet.classList.contains("is-closing");
}

export function closeSheetAnimated(sheet) {
  const finish = () => {
    closeTimer = null;
    sheet.classList.remove("is-closing", "is-opening");
    sheet.inert = false;
    sheet.hidden = true;
    sheet.innerHTML = "";
  };
  if (sheet.hidden || prefersReducedMotion()) {
    finish();
    return;
  }
  sheet.inert = true;
  sheet.classList.remove("is-opening");
  sheet.classList.add("is-closing");
  closeTimer = setTimeout(finish, tokenMs("--dur-base", 220) + 40);
}

// Numbers. Pure: whole cents between `from` and `to` at time t in [0, 1] (ease-out).
// t >= 1 always gives exactly `to`, so the last frame is the exact value.
export function easeOutCubic(t) {
  const u = 1 - t;
  return 1 - u * u * u;
}

export function interpolateCents(from, to, t) {
  if (!(t > 0)) return from;
  if (t >= 1) return to;
  return Math.round(from + (to - from) * easeOutCubic(t));
}

// Elements with data-count="key" data-cents="1234" count from the value last shown for that
// key to the new one. A change mid-way retargets from what is on screen now. The first time
// a key is seen, or with reduced motion, the value is simply shown.
const counters = new Map();

export function animateCounts(root, format) {
  root.querySelectorAll("[data-count]").forEach((el) => {
    const key = el.dataset.count;
    const to = Number(el.dataset.cents);
    const entry = counters.get(key);
    if (!entry || prefersReducedMotion()) {
      if (entry && entry.raf) cancelAnimationFrame(entry.raf);
      counters.set(key, { shown: to, to, raf: 0 });
      el.textContent = format(to);
      return;
    }
    if (entry.to === to) {
      el.textContent = format(entry.shown); // still running: the new element continues from here
      return;
    }
    if (entry.raf) cancelAnimationFrame(entry.raf);
    const from = entry.shown;
    const start = performance.now();
    const duration = tokenMs("--dur-count", 500);
    entry.to = to;
    el.textContent = format(from);
    const frame = (now) => {
      const t = (now - start) / duration;
      entry.shown = interpolateCents(from, to, t);
      const node = root.querySelector(`[data-count="${key}"]`);
      if (node) node.textContent = format(entry.shown);
      entry.raf = t < 1 ? requestAnimationFrame(frame) : 0;
    };
    entry.raf = requestAnimationFrame(frame);
  });
}

// Bars: data-bar="key" data-ratio="0.4" data-tone="near". The fill grows with scaleX from the
// last ratio shown, and the colour fades between tones (two frames so the start is painted).
const bars = new Map();

export function animateBars(root) {
  root.querySelectorAll("[data-bar]").forEach((el) => {
    const key = el.dataset.bar;
    const ratio = Number(el.dataset.ratio);
    const tone = el.dataset.tone || "";
    const bar = el.parentElement;
    const apply = (r, t) => {
      el.style.transform = `scaleX(${r})`;
      bar.classList.remove("near", "over");
      if (t) bar.classList.add(t);
    };
    const prev = bars.get(key);
    bars.set(key, { ratio, tone });
    if (!prev || prefersReducedMotion() || (prev.ratio === ratio && prev.tone === tone)) {
      apply(ratio, tone);
      return;
    }
    apply(prev.ratio, prev.tone);
    requestAnimationFrame(() => requestAnimationFrame(() => apply(ratio, tone)));
  });
}

// Lists. Elements with data-key are compared with the last render of the same view: new ones
// slide in. When a view appears (a screen change, a new map filter), its rows stagger in,
// STAGGER_MAX at most so a long list never feels slow.
const STAGGER_MAX = 8;
const seenKeys = new Map();

export function animateEntrances(root, viewKey, entering) {
  const els = [...root.querySelectorAll("[data-key]")];
  const prev = seenKeys.get(viewKey);
  seenKeys.set(viewKey, new Set(els.map((el) => el.dataset.key)));
  if (prefersReducedMotion()) return;
  const fresh = entering || !prev || prev.size === 0;
  let index = 0;
  els.forEach((el) => {
    if (!fresh && prev.has(el.dataset.key)) return;
    el.style.setProperty("--i", String(fresh ? Math.min(index, STAGGER_MAX) : 0));
    el.classList.add("is-new");
    index += 1;
  });
}

// An element leaving (an undone payment): fade, then collapse. Resolves when it is gone,
// or at once with reduced motion. Never waits longer than the slow token.
export function leaveElement(el) {
  if (!el || prefersReducedMotion()) return Promise.resolve();
  el.style.setProperty("--h", `${el.offsetHeight}px`);
  el.classList.add("is-leaving");
  return new Promise((resolve) => setTimeout(resolve, tokenMs("--dur-slow", 360)));
}

// The nav pill slides under the current tab (no slide on the first placement).
export function moveNavPill(nav) {
  const pill = nav.querySelector("#nav-pill");
  const on = nav.querySelector("button.on");
  if (!pill) return;
  if (!on) {
    pill.hidden = true;
    return;
  }
  pill.hidden = false;
  pill.style.transform = `translate(${on.offsetLeft}px, ${on.offsetTop}px)`;
  pill.style.width = `${on.offsetWidth}px`;
  pill.style.height = `${on.offsetHeight}px`;
  if (!pill.classList.contains("ready")) requestAnimationFrame(() => pill.classList.add("ready"));
}

// Fund tanks. Each .tank-water (data-tank="main" data-level="8571" in basis points) is a full
// height block moved down by translateY, so the wave on its surface is never stretched.
// render() replaces the HTML, so captureTanks() reads the level each column shows right now
// (mid-animation too) and animateTanks() continues from there to the server's level. A newer
// render always wins (tankGen), so fast clicks or a screen change still end on the real levels.
export const TANK_FULL = 10000;
const tankTargets = new Map(); // fund -> the last level asked for
let tankShown = null; // fund -> level on screen just before the current render
let tankGen = 0;

export function waterTransform(level) {
  const clamped = Math.min(Math.max(Number(level) || 0, 0), TANK_FULL);
  return `translateY(${(TANK_FULL - clamped) / 100}%)`;
}

function shownLevel(water) {
  const height = water.offsetHeight;
  const matrix = getComputedStyle(water).transform;
  if (!height || !matrix || matrix === "none") return null;
  const parts = matrix.slice(matrix.indexOf("(") + 1, -1).split(",").map(Number);
  const ty = parts.length === 6 ? parts[5] : parts[13];
  if (!Number.isFinite(ty)) return null;
  return Math.round(TANK_FULL * (1 - ty / height));
}

export function captureTanks(root) {
  const waters = root.querySelectorAll("[data-tank]");
  if (!waters.length) {
    tankShown = null;
    return;
  }
  tankShown = new Map();
  waters.forEach((el) => {
    const level = shownLevel(el);
    if (level != null) tankShown.set(el.dataset.tank, level);
  });
}

function placeWater(el, level, animate) {
  el.classList.toggle("no-move", !animate);
  el.style.transform = waterTransform(level);
}

function tankMs() {
  return tokenMs("--dur-slow", 360) * 2.5;
}

// The other funds that paid part of a payment (a reallocation, or Snacks covering a meal).
function flowMoves(flow, waters) {
  if (!flow || !flow.from || !waters.has(flow.category)) return [];
  return Object.entries(flow.from)
    .filter(([fund, cents]) => fund !== flow.category && cents > 0 && waters.has(fund))
    .map(([fund, cents]) => ({ fund, cents, water: waters.get(fund) }));
}

// Droplets from the surface of each source column to the top of the target column.
function pour(root, moves, target, startLevels, ms) {
  const box = root.querySelector(".tanks");
  const goal = target.parentElement;
  if (!box || !goal) return;
  const origin = box.getBoundingClientRect();
  const end = goal.getBoundingClientRect();
  const tx = end.left + end.width / 2 - origin.left;
  const ty = end.top - origin.top;
  moves.forEach(({ water }) => {
    const glass = water.parentElement.getBoundingClientRect();
    const level = startLevels.get(water.dataset.tank) / TANK_FULL;
    const sx = glass.left + glass.width / 2 - origin.left;
    const sy = glass.top + glass.height * (1 - level) - origin.top;
    const peak = Math.min(sy, ty) - 28;
    const color = getComputedStyle(water).backgroundColor;
    for (let i = 0; i < 6; i += 1) {
      const drop = document.createElement("span");
      drop.className = "tank-drop";
      drop.setAttribute("aria-hidden", "true");
      drop.style.background = color;
      box.appendChild(drop);
      if (typeof drop.animate !== "function") {
        drop.remove();
        continue;
      }
      const run = drop.animate([
        { transform: `translate(${sx}px, ${sy}px) scale(0.6)`, opacity: 0 },
        { transform: `translate(${(sx + tx) / 2}px, ${peak}px) scale(1)`, opacity: 1, offset: 0.45 },
        { transform: `translate(${tx}px, ${ty}px) scale(0.7)`, opacity: 0.9, offset: 0.9 },
        { transform: `translate(${tx}px, ${ty + 6}px) scale(0.4)`, opacity: 0 },
      ], { duration: ms * 0.75, delay: i * (ms / 24), easing: "ease-in-out", fill: "both" });
      run.onfinish = () => drop.remove();
    }
  });
}

// Levels move from what is on screen to the server's levels. With a flow (the payment just
// saved used other funds), phase 1 pours: the sources drop to their final level while the
// target rises by what they gave; phase 2 drains the target to its final level. Only the
// visual is staged: every column ends on data-level. Reduced motion: levels jump, no stream.
export function animateTanks(root, flow) {
  const gen = ++tankGen;
  const before = tankShown;
  tankShown = null;
  const waters = new Map([...root.querySelectorAll("[data-tank]")].map((el) => [el.dataset.tank, el]));
  if (!waters.size) return;
  const reduce = prefersReducedMotion();
  const start = new Map();
  let moving = false;
  waters.forEach((el, fund) => {
    const to = Number(el.dataset.level);
    let from = before && before.has(fund) ? before.get(fund) : tankTargets.get(fund);
    if (from == null || reduce) from = to;
    tankTargets.set(fund, to);
    start.set(fund, from);
    if (from !== to) moving = true;
    placeWater(el, from, false);
  });
  if (reduce || !moving) return;
  const mid = new Map();
  const moves = flowMoves(flow, waters);
  const target = flow ? waters.get(flow.category) : null;
  const allocation = target ? Number(target.dataset.allocation) : 0;
  if (moves.length && allocation > 0) {
    const given = moves.reduce((sum, move) => sum + move.cents, 0);
    const from = start.get(flow.category);
    mid.set(flow.category, Math.min(from + Math.round((given * TANK_FULL) / allocation), TANK_FULL));
  }
  const ms = tankMs();
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (gen !== tankGen) return;
    waters.forEach((el, fund) => placeWater(el, mid.has(fund) ? mid.get(fund) : Number(el.dataset.level), true));
    if (!mid.size) return;
    pour(root, moves, target, start, ms);
    setTimeout(() => {
      if (gen === tankGen && target.isConnected) placeWater(target, Number(target.dataset.level), true);
    }, ms);
  }));
}
