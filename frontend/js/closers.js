// Every close control in one place.
//
// A close button carries data-close="<overlay name>". One click handler on the document finds it
// and calls that overlay's close(), so a button re-drawn by a render (innerHTML) can never lose its
// handler. Escape closes the top-most open overlay from anywhere (not only when focus is inside
// it), and a tap on a sheet's dimmed backdrop closes that sheet. Overlays register themselves with
// registerOverlay({ name, isOpen, close, layer }): a higher layer is on top.

const overlays = new Map();

export function registerOverlay({ name, isOpen, close, layer = 0 }) {
  overlays.set(name, { name, isOpen, close, layer });
}

export function closeOverlay(name) {
  const overlay = overlays.get(name);
  if (overlay && overlay.isOpen()) overlay.close();
}

// The open overlay on top, or null.
export function topOverlay() {
  let top = null;
  for (const overlay of overlays.values()) {
    if (overlay.isOpen() && (!top || overlay.layer > top.layer)) top = overlay;
  }
  return top;
}

// Sets innerHTML only when it changed, so an unchanged re-render (the status bar clock re-draws
// the home screen every 15 s) does not replace a button between press and release.
const lastHtml = new WeakMap();

export function setHtml(el, html) {
  if (!el || lastHtml.get(el) === html) return false;
  el.innerHTML = html;
  lastHtml.set(el, html);
  return true;
}

document.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-close]");
  if (btn) {
    event.preventDefault();
    closeOverlay(btn.dataset.close);
    return;
  }
  // A tap on the dimmed backdrop of a sheet (the sheet element itself, outside its panel).
  const backdrop = event.target.closest("[data-backdrop]");
  if (backdrop && event.target === backdrop) closeOverlay(backdrop.dataset.backdrop);
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || event.defaultPrevented) return;
  if (document.getElementById("tour")) return; // the tour handles its own Escape
  const top = topOverlay();
  if (!top) return;
  event.preventDefault();
  top.close();
});
