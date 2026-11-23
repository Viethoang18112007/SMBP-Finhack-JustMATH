// In-phone notifications, simulated and offline (no OS permission, nothing leaves the page).
//
// - Banner: slides down from the top of the phone screen, hides after BANNER_MS, closes with its X,
//   Escape or a swipe up; a tap opens the screen it is about.
// - Notification centre: tap the status bar or swipe down from it. Lists every notification of
//   this session, newest first, with "Clear all".
// - Badge: the unread count, in red on the SSUST app icon.
// - Triggers (RULES): each one reads the app state and returns the notifications it calls for. They
//   run after every render; a key per notification (mode + day or week + item) makes each one fire
//   once, remembered in the browser. The auto-play switches them off and fires each one by name at
//   an exact time with fire(kind), so the demo is deterministic.

import { registerOverlay } from "./closers.js";
import { NATIVE } from "./config.js";
import { hkTime, isFramed, openApp } from "./device.js";
import { escapeHtml, hk } from "./format.js";
import { paymentNote } from "./inbox.js";
import { state } from "./store.js";

export const BANNER_MS = 4000;
const SWIPE_PX = 30;
const SEEN_KEY = "ssust.notified";
const SEEN_MAX = 200;

const notes = []; // newest first
let nextId = 1;
let auto = true;
let bannerId = null;
let bannerTimer = null;
let centerOpen = false;

function el(id) {
  return document.getElementById(id);
}

function seenKeys() {
  try {
    return new Set(JSON.parse(localStorage.getItem(SEEN_KEY) || "[]"));
  } catch (err) {
    return memorySeen;
  }
}
const memorySeen = new Set();

function remember(key) {
  memorySeen.add(key);
  try {
    const keys = [...seenKeys(), key].slice(-SEEN_MAX);
    localStorage.setItem(SEEN_KEY, JSON.stringify(keys));
  } catch (err) {
    // Storage blocked: remembered for this page only.
  }
}

// The five triggers. Each returns a list of notifications: { key, app, title, body, tag?, open }.
// open: { screen, review?, target? } says what a tap shows.
const RULES = {
  daily(data) {
    if (!data.view || !data.view.ready) return [];
    return [{
      key: `daily:${data.mode}:${data.today}`, app: "SSUST",
      title: `Today: ${hk(Math.max(data.view.todayRemaining, 0))} for food`,
      body: "Your daily allowance: food money left divided by the days left, today included.",
      open: { screen: "today", target: ".hero" },
    }];
  },
  weekClosed(data) {
    const pot = data.savingsPot;
    if (!pot || !pot.lastWeek || !(pot.total > 0)) return [];
    return [{
      key: `closed:${data.mode}:${pot.lastWeek}`, app: "SSUST",
      title: "Week closed",
      body: `${hk(pot.lastFlexMoved)} left in your flexible funds moved to Long-term Savings (now ${hk(pot.total)}).`,
      open: { screen: "week" },
    }];
  },
  fundEmpty(data) {
    const ins = data.insights;
    if (!ins || !ins.ready) return [];
    return ins.warnings.filter((w) => w.fund !== "food").map((w) => ({
      key: `empty:${data.mode}:${data.weekStart}:${w.fund}`, app: "SSUST",
      title: "A fund may run out before Sunday",
      body: `${w.title}. ${w.text}`,
      open: { screen: "today", target: ".ins-card" },
    }));
  },
  tooFast(data) {
    const proj = data.projection;
    if (!proj || !proj.ready || proj.status !== "too_fast") return [];
    return [{
      key: `fast:${data.mode}:${data.today}`, app: "SSUST",
      title: "Spending too fast",
      body: `At this pace: ${hk(proj.projected30)} in the next 30 days, for a budget of ${hk(proj.budget30)}.`,
      open: { screen: "today", target: "#projection-card" },
    }];
  },
  payment(data) {
    return (data.inbox || []).map((item) => paymentNote(item, data.mode));
  },
};
const ORDER = ["daily", "weekClosed", "fundEmpty", "tooFast", "payment"];

// After every render: run the triggers (unless the auto-play drives them).
export function checkNotifications() {
  // The iPhone app has no simulated phone: no fake banners over the real one.
  if (NATIVE || !auto || !state.data || state.data.past) return;
  const seen = seenKeys();
  for (const kind of ORDER) {
    for (const note of RULES[kind](state.data)) {
      if (seen.has(note.key) || memorySeen.has(note.key)) continue;
      remember(note.key);
      notify(note);
    }
  }
}

export function setAutoNotify(on) {
  auto = Boolean(on);
}

// The auto-play: fire one trigger now, from the current state, even if it fired before.
export function fire(kind) {
  const list = RULES[kind] ? RULES[kind](state.data || {}) : [];
  const note = kind === "payment" ? list[list.length - 1] : list[0];
  if (note) notify(note);
  return Boolean(note);
}

// Forget the session's notifications (the auto-play starts and ends clean).
export function resetNotifications() {
  notes.length = 0;
  hideBanner();
  closeCenter();
  renderBadge();
}

// Show a notification that just happened (a new tap): always shown, and its key is remembered so
// the triggers do not show it a second time.
export function notifyArrival(note) {
  remember(note.key);
  return notify(note);
}

export function notify(note) {
  const item = { ...note, id: nextId++, time: hkTime(), read: false };
  notes.unshift(item);
  renderBadge();
  if (centerOpen) renderCenter();
  else showBanner(item);
  return item.id;
}

function noteHtml(item, where) {
  const tag = item.tag || "";
  return `<span class="notify-head"><span class="notify-app">${escapeHtml(item.app)}</span>${tag}<span class="notify-time">${escapeHtml(item.time)}</span></span>
      <span class="notify-body"><strong>${escapeHtml(item.title)}</strong></span>
      <span class="notify-foot">${escapeHtml(item.body)}</span>${where === "banner" ? "" : ""}`;
}

function showBanner(item) {
  const box = el("notify");
  if (!box) return;
  bannerId = item.id;
  box.innerHTML = `<button type="button" class="notify-x" data-close="notify" aria-label="Close the notification">✕</button>`
    + `<button type="button" class="notify-card" data-note-open="${item.id}" aria-label="${escapeHtml(`${item.app}: ${item.title}. ${item.body}`)}">${noteHtml(item, "banner")}</button>`;
  box.style.transform = "";
  box.hidden = false;
  box.classList.remove("is-in");
  void box.offsetWidth;
  box.classList.add("is-in");
  clearTimeout(bannerTimer);
  bannerTimer = setTimeout(hideBanner, BANNER_MS);
}

export function hideBanner() {
  clearTimeout(bannerTimer);
  bannerId = null;
  const box = el("notify");
  if (!box) return;
  box.hidden = true;
  box.classList.remove("is-in");
  box.style.transform = "";
}

function renderBadge() {
  const icon = el("ssust-icon");
  if (!icon) return;
  let badge = icon.querySelector(".app-badge");
  if (!badge) {
    badge = document.createElement("span");
    badge.className = "app-badge";
    badge.setAttribute("aria-hidden", "true");
    icon.appendChild(badge);
  }
  const unread = notes.filter((n) => !n.read).length;
  badge.textContent = unread > 99 ? "99+" : String(unread);
  badge.hidden = unread === 0;
  icon.setAttribute("aria-label", unread ? `SSUST, ${unread} new notification${unread > 1 ? "s" : ""}` : "SSUST");
}

function renderCenter() {
  const box = el("notify-center");
  if (!box) return;
  const items = notes.map((n) => `<li><button type="button" class="nc-item${n.read ? "" : " unread"}" data-note-open="${n.id}">${noteHtml(n, "center")}</button></li>`).join("");
  box.innerHTML = `<div class="nc-panel" role="dialog" aria-modal="true" aria-labelledby="nc-title">
      <div class="nc-head"><h2 id="nc-title">Notifications</h2>
        <button type="button" class="ghost small" data-nc-clear${notes.length ? "" : " disabled"}>Clear all</button>
        <button type="button" class="nc-x" data-close="center" aria-label="Close notifications">✕</button></div>
      ${items ? `<ul class="nc-list">${items}</ul>` : `<p class="nc-empty">No notifications</p>`}
      <p class="nc-note">Simulated notifications inside this demo phone.</p>
    </div>`;
}

export function openCenter() {
  const box = el("notify-center");
  if (!box || centerOpen) return;
  hideBanner();
  centerOpen = true;
  notes.forEach((n) => { n.read = true; });
  renderBadge();
  renderCenter();
  box.hidden = false;
  box.classList.remove("is-in");
  void box.offsetWidth;
  box.classList.add("is-in");
  box.querySelector(".nc-x")?.focus();
}

export function closeCenter() {
  const box = el("notify-center");
  centerOpen = false;
  if (box) box.hidden = true;
}

export function clearAll() {
  notes.length = 0;
  renderBadge();
  if (centerOpen) renderCenter();
}

// A tap on a banner or a centre item: show what it is about.
export function openNote(id) {
  const item = notes.find((n) => n.id === id);
  hideBanner();
  closeCenter();
  if (!item) return;
  item.read = true;
  renderBadge();
  const open = item.open || { screen: "today" };
  state.sheet = null;
  state.adding = false;
  openApp(open.review ? "review" : open.screen, null);
  if (open.target) document.querySelector(open.target)?.scrollIntoView({ block: "start", behavior: "smooth" });
}

function initNotifications() {
  document.addEventListener("click", (event) => {
    const open = event.target.closest("[data-note-open]");
    if (open) {
      openNote(Number(open.dataset.noteOpen));
      return;
    }
    if (event.target.closest("[data-nc-clear]")) clearAll();
  });
  // Swipe the banner up to dismiss it.
  const banner = el("notify");
  let swipe = null;
  banner?.addEventListener("pointerdown", (event) => {
    if (event.target.closest("[data-close]")) return;
    swipe = { y: event.clientY, id: event.pointerId, moved: false };
  });
  banner?.addEventListener("pointermove", (event) => {
    if (!swipe || event.pointerId !== swipe.id) return;
    const dy = Math.min(event.clientY - swipe.y, 0);
    if (Math.abs(dy) > 6 && !swipe.moved) {
      swipe.moved = true;
      clearTimeout(bannerTimer);
      banner.setPointerCapture(swipe.id);
    }
    if (swipe.moved) banner.style.transform = `translate(-50%, ${dy}px)`;
  });
  const endSwipe = (event) => {
    if (!swipe || event.pointerId !== swipe.id) return;
    const dy = event.clientY - swipe.y;
    const moved = swipe.moved;
    swipe = null;
    if (!moved) return;
    if (dy < -SWIPE_PX) hideBanner();
    else {
      banner.style.transform = "";
      bannerTimer = setTimeout(hideBanner, BANNER_MS);
    }
    // The click that ends a swipe does not open the notification.
    banner.addEventListener("click", (e) => { e.stopPropagation(); e.preventDefault(); }, { capture: true, once: true });
  };
  banner?.addEventListener("pointerup", endSwipe);
  banner?.addEventListener("pointercancel", endSwipe);
  // The status bar: a tap or a swipe down opens the centre (phone view only).
  const bar = el("statusbar");
  let pull = null;
  bar?.addEventListener("pointerdown", (event) => { pull = { y: event.clientY, id: event.pointerId }; });
  document.addEventListener("pointerup", (event) => {
    if (!pull || event.pointerId !== pull.id) return;
    const dy = event.clientY - pull.y;
    pull = null;
    if (dy > SWIPE_PX && isFramed()) openCenter();
  });
  bar?.addEventListener("click", () => { if (isFramed()) openCenter(); });
  bar?.addEventListener("keydown", (event) => {
    if ((event.key === "Enter" || event.key === " ") && isFramed()) {
      event.preventDefault();
      openCenter();
    }
  });
  renderBadge();
}

registerOverlay({ name: "notify", layer: 30, isOpen: () => bannerId !== null, close: hideBanner });
registerOverlay({ name: "center", layer: 35, isOpen: () => centerOpen, close: closeCenter });

initNotifications();
