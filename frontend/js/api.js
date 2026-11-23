// JSON calls to the SSUST server (same origin on the web, API_BASE in the iOS shell).

import { NATIVE, apiUrl, deviceId } from "./config.js";

export async function api(path, body) {
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
  return data;
}
