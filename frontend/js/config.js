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
