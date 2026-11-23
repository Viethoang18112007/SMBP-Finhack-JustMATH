// A visible pointer for screen-recording the auto-play demo (?record=1 or ?cursor=1).
//
// It glides to a control, dips with a blue ring (the click effect), then tour.js does the real
// click. It is a picture only: aria-hidden, pointer-events none, never in the way of the app.
// Positions use element.style (the CSP blocks inline style attributes).

import { prefersReducedMotion } from "./motion.js";

const EASE = "cubic-bezier(0.45,0.05,0.25,1)";
const SCROLLERS = "#screen, #phone, #home, #cam-screen";

let cursor = null;
let at = { x: 0, y: 0 };

function param(name) {
  try {
    return new URLSearchParams(window.location.search).get(name) === "1";
  } catch (err) {
    return false;
  }
}

// ?record=1: the clean recording mode (captions only, pointer, Space starts, Esc stops).
export function recordMode() {
  return param("record");
}

// The pointer alone, with the normal caption and controls: ?cursor=1 (or record mode).
export function cursorWanted() {
  return recordMode() || param("cursor");
}

export function cursorOn() {
  return Boolean(cursor && cursor.isConnected);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Always inside the window, so the pointer never leaves the video.
function place(point, ms) {
  const x = Math.min(Math.max(point.x, 4), window.innerWidth - 24);
  const y = Math.min(Math.max(point.y, 4), window.innerHeight - 28);
  at = { x: Math.round(x), y: Math.round(y) };
  cursor.style.transition = ms > 0 ? `transform ${ms}ms ${EASE}` : "none";
  cursor.style.transform = `translate(${at.x}px, ${at.y}px)`;
}

export function showCursor(aroundEl) {
  hideCursor();
  cursor = document.createElement("div");
  cursor.className = "ghost-cursor";
  cursor.setAttribute("aria-hidden", "true");
  cursor.innerHTML = `<span class="ghost-ring"></span><svg class="ghost-arrow" width="28" height="28" viewBox="0 0 28 28" focusable="false">
      <path d="M5 3 L5 22 L10 17.5 L13.6 25 L17 23.4 L13.5 16.2 L20 16.2 Z" fill="#fff" stroke="#0f172a" stroke-width="1.6" stroke-linejoin="round"/>
    </svg>`;
  document.body.appendChild(cursor);
  const r = aroundEl ? aroundEl.getBoundingClientRect() : null;
  const start = r && r.width
    ? { x: r.left + r.width * 0.62, y: r.top + r.height * 0.55 }
    : { x: window.innerWidth / 2, y: window.innerHeight / 2 };
  place(start, 0);
}

export function hideCursor() {
  if (cursor) cursor.remove();
  cursor = null;
}

// The visible middle of an element (or a point near its top-left for "top"), clipped to the
// viewport and to the phone part that scrolls it.
export function aimAt(el, where = "center") {
  const r = el.getBoundingClientRect();
  let x1 = r.left; let y1 = r.top; let x2 = r.right; let y2 = r.bottom;
  const clip = el.parentElement && el.parentElement.closest(SCROLLERS);
  if (clip) {
    const c = clip.getBoundingClientRect();
    x1 = Math.max(x1, c.left); y1 = Math.max(y1, c.top); x2 = Math.min(x2, c.right); y2 = Math.min(y2, c.bottom);
  }
  x1 = Math.max(x1, 0); y1 = Math.max(y1, 0);
  x2 = Math.min(x2, window.innerWidth); y2 = Math.min(y2, window.innerHeight);
  const w = Math.max(0, x2 - x1);
  const h = Math.max(0, y2 - y1);
  if (where === "top") return { x: x1 + Math.min(w / 2, 120), y: y1 + Math.min(h / 2, 28) };
  return { x: x1 + w / 2, y: y1 + h / 2 };
}

// Glide to a point or an element; resolves once the move is done.
export async function moveTo(target, ms) {
  if (!cursorOn()) return;
  const point = target instanceof Element ? aimAt(target) : target;
  const distance = Math.hypot(point.x - at.x, point.y - at.y);
  let time = ms != null ? ms : Math.min(650, Math.max(280, 220 + distance * 0.75));
  if (prefersReducedMotion() || distance < 1) time = 0;
  place(point, time);
  if (time) await sleep(time);
}

// Stick to a point with no transition (drags and sliders).
export function follow(point) {
  if (cursorOn()) place(point, 0);
}

export function press(down) {
  if (cursorOn()) cursor.classList.toggle("is-down", Boolean(down));
}

// The click: the arrow dips and a blue ring grows and fades.
export async function clickEffect() {
  if (!cursorOn()) return;
  cursor.classList.remove("is-click");
  void cursor.offsetWidth; // restart the animation
  cursor.classList.add("is-click");
  await sleep(prefersReducedMotion() ? 0 : 170);
}

// The record-mode hint: Space (outside a text field) starts the demo.
export function showRecordHint(onStart) {
  document.getElementById("record-hint")?.remove();
  const hint = document.createElement("div");
  hint.className = "record-hint";
  hint.id = "record-hint";
  hint.setAttribute("role", "status");
  hint.textContent = "Record mode: press Space to start the demo. Esc stops it.";
  document.body.appendChild(hint);
  const onKey = (event) => {
    if (event.key !== " " && event.code !== "Space") return;
    if (event.target.closest && event.target.closest("input, textarea, select, [contenteditable]")) return;
    if (document.getElementById("tour")) return;
    event.preventDefault();
    document.removeEventListener("keydown", onKey, true);
    hint.remove();
    onStart();
  };
  document.addEventListener("keydown", onKey, true);
}
