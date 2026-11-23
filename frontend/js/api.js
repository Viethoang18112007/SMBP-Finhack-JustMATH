// JSON calls to the SSUST server (same origin on the web, API_BASE in the iOS shell).

import { apiUrl } from "./config.js";

export async function api(path, body) {
  let res;
  try {
    res = await fetch(apiUrl(path), {
      method: body ? "POST" : "GET",
      headers: body ? { "Content-Type": "application/json" } : {},
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
