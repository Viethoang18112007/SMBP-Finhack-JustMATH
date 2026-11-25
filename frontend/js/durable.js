// Durable storage in the iPhone app: the official Capacitor Preferences plugin (iOS UserDefaults,
// kept until the app is deleted; the WebView's own storage can be cleared by iOS), with the WebView
// storage as a mirror. If the plugin is missing (an older app build) the mirror alone is used.
// Values are never logged: they hold personal spending data.

import { DEVICE_KEY, NATIVE, deviceId, useDeviceId } from "./config.js";

function preferences() {
  if (!NATIVE) return null;
  try {
    const cap = window.Capacitor;
    if (typeof cap.isPluginAvailable === "function" && !cap.isPluginAvailable("Preferences")) return null;
    const plugin = cap.Plugins && cap.Plugins.Preferences;
    return plugin && typeof plugin.get === "function" && typeof plugin.set === "function" ? plugin : null;
  } catch (err) {
    return null;
  }
}

// The text saved under `key`, or null.
export async function readDurable(key) {
  const plugin = preferences();
  if (plugin) {
    try {
      const answer = await plugin.get({ key });
      if (answer && typeof answer.value === "string") return answer.value;
    } catch (err) {
      // fall back to the mirror
    }
  }
  try {
    return window.localStorage.getItem(key);
  } catch (err) {
    return null;
  }
}

// Save `value` (text) under `key` in both places. True when at least one kept it.
export async function writeDurable(key, value) {
  let kept = false;
  const plugin = preferences();
  if (plugin) {
    try {
      await plugin.set({ key, value });
      kept = true;
    } catch (err) {
      // the mirror below may still keep it
    }
  }
  try {
    window.localStorage.setItem(key, value);
    kept = true;
  } catch (err) {
    // storage full or blocked
  }
  return kept;
}

// At launch, before any API call: the phone's id from durable storage. A phone that only had it in
// the WebView storage (an older build) moves it over, so its server data stays its own.
export async function loadDeviceId() {
  if (!NATIVE) return;
  const saved = await readDurable(DEVICE_KEY);
  const id = /^[0-9a-f]{32}$/.test(saved || "") ? saved : deviceId();
  useDeviceId(id);
  await writeDurable(DEVICE_KEY, id);
}
