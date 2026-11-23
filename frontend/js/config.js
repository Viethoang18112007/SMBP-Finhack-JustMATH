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
// keeps this phone's data apart from everyone else's. Kept in the app's storage; when storage
// is blocked it lasts until the app is closed.
const DEVICE_KEY = "ssust.device";
let memoryId = null;

function newId() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function deviceId() {
  try {
    let id = window.localStorage.getItem(DEVICE_KEY);
    if (!/^[0-9a-f]{32}$/.test(id || "")) {
      id = newId();
      window.localStorage.setItem(DEVICE_KEY, id);
    }
    return id;
  } catch (err) {
    memoryId = memoryId || newId();
    return memoryId;
  }
}
