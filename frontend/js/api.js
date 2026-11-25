// JSON calls to the SSUST server (same origin on the web, API_BASE in the iOS shell).

import { NATIVE, apiUrl, deviceId } from "./config.js";

// Offline in the iPhone app: the last saved numbers are on screen and nothing can be changed.
const OFFLINE_WRITE = "You're offline: these are your last saved numbers. Changes are paused until the server answers.";
// Sent while still offline, right after the server answers again: the phone's own copy going back.
const RESTORE_PATH = "/api/restore";
// POST routes that only read: no backup needed after them.
const READ_ONLY_POSTS = new Set(["/api/receipt/parse", "/api/assistant/parse"]);
let readOnly = false;
const writeListeners = [];

export function setReadOnly(on) {
  readOnly = Boolean(on);
}

// Called with the path after every successful change (sync.js refreshes the phone's copy).
export function onApiWrite(listener) {
  writeListeners.push(listener);
}

// The iPhone app's first call: a free host sleeps when idle, and this starts waking it while the
// app loads. The answer does not matter.
export function wake() {
  if (!NATIVE) return;
  try {
    fetch(apiUrl("/api/ping"), { cache: "no-store" }).catch(() => {});
  } catch (err) {
    // the real calls report the problem
  }
}

export async function api(path, body) {
  if (body && readOnly && path !== RESTORE_PATH) {
    throw new Error(OFFLINE_WRITE);
  }
  let res;
  const headers = body ? { "Content-Type": "application/json" } : {};
  // The iPhone app: this phone's own data on the server (the web app sends nothing extra).
  if (NATIVE) headers["X-SSUST-Device"] = deviceId();
  try {
    res = await fetch(apiUrl(path), {
      method: body ? "POST" : "GET",
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    throw new Error("Could not reach the SSUST server. Check that it is still running, then try again.");
  }
  let data = {};
  try {
    data = await res.json();
  } catch (err) {
    data = {};
  }
  if (!res.ok) {
    const err = new Error(data.error || "The server refused that.");
    err.field = data.field || null; // the form field the error is about, when the server names one
    err.minimum = Number.isInteger(data.minimum) ? data.minimum : null; // the lowest allowed amount, in cents
    err.fromServer = true;
    throw err;
  }
  if (body && !READ_ONLY_POSTS.has(path)) {
    for (const listener of writeListeners) {
      try {
        listener(path);
      } catch (err) {
        // a listener never breaks the call
      }
    }
  }
  return data;
}
