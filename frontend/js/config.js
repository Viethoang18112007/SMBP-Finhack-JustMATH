// Where the API lives, and whether the app runs inside the iOS shell (Capacitor).
// On the web the page and the API share one origin, so API_BASE is "" and every call stays
// relative (/api/...), exactly as before. Inside the iOS app the page comes from the app bundle,
// so the calls go to the hosted server instead: the Render service ssust-api (render.yaml,
// serve.py, demo mode). Its free plan sleeps when idle and wipes the data on every restart.

export const NATIVE_API_BASE = "https://ssust-api.onrender.com";

// The iOS shell injects window.Capacitor; a normal browser has none.
function detectNative() {
  try {
    return Boolean(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform());
  } catch (err) {
    return false;
  }
}

export const NATIVE = detectNative();
export const API_BASE = NATIVE ? NATIVE_API_BASE : "";

export function apiUrl(path) {
  return API_BASE + path;
}

// The iPhone app's own id (random, 32 hex characters), sent with every API call so the server
// keeps this phone's data apart from everyone else's. At launch durable.js loadDeviceId() reads it
// from the app's durable storage (iOS keeps it until the app is deleted) and pins it here; before
// that, or without it, it comes from the WebView storage; when that is blocked too it lasts until
// the app is closed.
export const DEVICE_KEY = "ssust.device";
const DEVICE_PATTERN = /^[0-9a-f]{32}$/;
let memoryId = null;
let pinnedId = null;

function newId() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

// Use this id from now on (the one kept in durable storage). It is mirrored to the WebView storage.
export function useDeviceId(id) {
  if (!DEVICE_PATTERN.test(id || "")) return;
  pinnedId = id;
  try {
    window.localStorage.setItem(DEVICE_KEY, id);
  } catch (err) {
    // the pinned id still holds until the app is closed
  }
}

export function deviceId() {
  if (pinnedId) return pinnedId;
  try {
    let id = window.localStorage.getItem(DEVICE_KEY);
    if (!DEVICE_PATTERN.test(id || "")) {
      id = newId();
      window.localStorage.setItem(DEVICE_KEY, id);
    }
    return id;
  } catch (err) {
    memoryId = memoryId || newId();
    return memoryId;
  }
}
