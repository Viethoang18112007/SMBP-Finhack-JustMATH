// The simulated phone around the app on wide screens: the frame, a status bar with the Hong Kong
// time, a home screen with the SSUST icon and widgets, and the home bar that goes back to it.
// On narrow screens (a real phone) none of this shows: the app is full screen.

import { setHtml } from "./closers.js";
import { NATIVE } from "./config.js";
import { checkNotifications } from "./notifications.js";
import { refreshMapSize } from "./mapview.js";
import { render } from "./render.js";
import { state } from "./store.js";
import { renderQuick } from "./widget.js";
import { widgetsHtml } from "./widgets.js";

const WIDE = "(min-width: 901px)";
const wide = window.matchMedia ? window.matchMedia(WIDE) : { matches: false, addEventListener() {} };
const CLOCK = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Hong_Kong", hour: "2-digit", minute: "2-digit", hour12: false });

export function hkTime(date = new Date()) {
  return CLOCK.format(date);
}

// True while the app is drawn inside the phone frame. Never in the iOS shell: the app is already
// on a real phone, so there is no fake frame and no simulated home screen.
export function isFramed() {
  return Boolean(!NATIVE && state.phoneView && wide.matches);
}

// True while the home screen covers the app (framed only).
export function onHome() {
  return isFramed() && state.deviceView === "home";
}

function el(id) {
  return document.getElementById(id);
}

// Frame on or off, home screen or app: classes, hidden and inert follow the state.
export function applyFrame() {
  const framed = isFramed();
  const home = framed && state.deviceView === "home";
  document.body.classList.toggle("phone-view", framed);
  const device = el("device");
  if (device) device.dataset.view = home ? "home" : "app";
  if (el("home")) el("home").hidden = !home;
  if (el("phone")) el("phone").inert = home;
  if (el("desk-side")) el("desk-side").hidden = !framed;
  renderHome();
}

// The widgets read the same state as the app; called after every render.
export function renderHome() {
  const box = el("home-widgets");
  if (!box) return;
  const html = state.data ? widgetsHtml(state, hkTime(state.updatedAt || new Date())) : "";
  // Bar fills through element.style: the CSP blocks inline style attributes.
  if (setHtml(box, html)) box.querySelectorAll("[data-w-level]").forEach((bar) => { bar.style.width = `${bar.dataset.wLevel}%`; });
  renderQuick();
  checkNotifications();
}

export function showHome() {
  if (!isFramed()) return;
  state.deviceView = "home";
  applyFrame();
  el("ssust-icon")?.focus();
}

// Open the app from the home screen (icon or widget), with a short zoom from where it was tapped.
// `from` is the tapped element or its rect, read before it was re-rendered; a hidden one (no
// size) zooms from the middle of the phone instead of the corner of the screen.
export function openApp(screen, from) {
  state.deviceView = "app";
  const review = screen === "review";
  if (review) screen = "today";
  if (screen && state.data && state.view && state.view.ready) state.screen = screen;
  applyFrame();
  render();
  const phone = el("phone");
  if (phone && from && isFramed()) {
    const box = phone.getBoundingClientRect();
    const r = typeof from.getBoundingClientRect === "function" ? from.getBoundingClientRect() : from;
    const shown = r.width > 0 && r.height > 0;
    const x = shown ? r.left + r.width / 2 - box.left : box.width / 2;
    const y = shown ? r.top + r.height / 2 - box.top : box.height / 2;
    phone.style.transformOrigin = `${x}px ${y}px`;
    phone.classList.remove("app-zoom");
    void phone.offsetWidth; // restart the animation
    phone.classList.add("app-zoom");
    phone.addEventListener("animationend", () => phone.classList.remove("app-zoom"), { once: true });
  }
  if (review) document.getElementById("review-card")?.scrollIntoView({ block: "start" });
  refreshMapSize();
  setTimeout(refreshMapSize, 0);
}

// The home screen pager: pages side by side, snapped on x. Touch swipes are native scrolling; a
// mouse drags it with pointer events; arrow keys and the page dots move one page. A drag never
// counts as a tap on what is under the pointer.
const DRAG_PX = 6;
let homePage = 0;

export function currentPage() {
  return homePage;
}

function pages() {
  return el("home-pager") ? el("home-pager").querySelectorAll(".home-page").length : 0;
}

function markDots(index) {
  homePage = index;
  document.querySelectorAll("[data-page-dot]").forEach((dot) => {
    const on = Number(dot.dataset.pageDot) === index;
    dot.classList.toggle("on", on);
    if (on) dot.setAttribute("aria-current", "true");
    else dot.removeAttribute("aria-current");
  });
}

export function goToPage(index, smooth = true) {
  const pager = el("home-pager");
  if (!pager) return;
  const target = Math.max(0, Math.min(pages() - 1, index));
  pager.scrollTo({ left: target * pager.clientWidth, behavior: smooth && !reduceMotion() ? "smooth" : "auto" });
  markDots(target);
}

function reduceMotion() {
  return window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)").matches : false;
}

function initPager() {
  const pager = el("home-pager");
  if (!pager) return;
  let drag = null;
  let dragged = false;
  pager.addEventListener("scroll", () => {
    if (drag || !pager.clientWidth) return;
    const index = Math.round(pager.scrollLeft / pager.clientWidth);
    if (index !== homePage) markDots(index);
  }, { passive: true });
  pager.addEventListener("pointerdown", (event) => {
    if (event.pointerType !== "mouse" || event.button !== 0 || event.target.closest("input, textarea, select")) return;
    drag = { x: event.clientX, left: pager.scrollLeft, id: event.pointerId };
    dragged = false;
  });
  pager.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.id) return;
    const dx = event.clientX - drag.x;
    if (!dragged && Math.abs(dx) < DRAG_PX) return;
    if (!dragged) {
      dragged = true;
      pager.classList.add("dragging");
      pager.setPointerCapture(drag.id);
    }
    pager.scrollLeft = drag.left - dx;
  });
  const end = (event) => {
    if (!drag || event.pointerId !== drag.id) return;
    const dx = event.clientX - drag.x;
    const start = Math.round(drag.left / (pager.clientWidth || 1));
    drag = null;
    if (!dragged) return;
    pager.classList.remove("dragging");
    // A quarter of a page is enough to turn it, like a flick.
    const turn = Math.abs(dx) > pager.clientWidth / 4 ? (dx < 0 ? 1 : -1) : 0;
    goToPage(start + turn);
  };
  pager.addEventListener("pointerup", end);
  pager.addEventListener("pointercancel", end);
  // The click that ends a drag is not a tap.
  pager.addEventListener("click", (event) => {
    if (!dragged) return;
    dragged = false;
    event.preventDefault();
    event.stopPropagation();
  }, true);
  document.addEventListener("keydown", (event) => {
    if (!onHome() || document.getElementById("tour") || event.target.closest("input, textarea, select")) return;
    if (!el("cam-screen")?.hidden) return;
    if (event.key === "ArrowLeft") goToPage(homePage - 1);
    else if (event.key === "ArrowRight") goToPage(homePage + 1);
    else return;
    event.preventDefault();
  });
  document.querySelectorAll("[data-page-dot]").forEach((dot) => dot.addEventListener("click", () => goToPage(Number(dot.dataset.pageDot))));
  // Keep the page in place when the frame is resized.
  window.addEventListener("resize", () => goToPage(homePage, false));
}

let lastDay = "";

function tick() {
  const time = el("sb-time");
  if (time) time.textContent = hkTime();
  // A new day in Hong Kong: the widgets refresh with the server's new numbers.
  const day = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Hong_Kong" }).format(new Date());
  if (lastDay && day !== lastDay) document.dispatchEvent(new CustomEvent("ssust:new-day"));
  lastDay = day;
  renderHome();
}

export function initDevice() {
  initPager();
  tick();
  setInterval(tick, 15000);
  el("home-bar")?.addEventListener("click", showHome);
  el("home")?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-open-app]");
    if (btn) openApp(btn.dataset.openApp, btn);
  });
  wide.addEventListener?.("change", () => {
    applyFrame();
    refreshMapSize();
  });
  applyFrame();
}
