// Checks what a receipt scan says when it fails (frontend/js/scanerror.js), that reading a receipt is
// not blocked by the offline pause (frontend/js/api.js), and the phone reader's own failures
// (frontend/js/scanner.js readNative). Run by hand (Node 18 or later):
//   node tools/check_scan_js.mjs
// The modules are loaded from their text; their imports are replaced by small stubs.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const text = (path) => readFileSync(new URL(`../frontend/js/${path}`, import.meta.url), "utf8");
const load = (source) => import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));

// Messages, one per stage.
const S = await load(text("scanerror.js"));
const coded = (code, message = "x") => Object.assign(new Error(message), { code });
assert.equal(S.scanFailure("plugin", coded("failed")), "The phone's scanner failed (failed). Scan again, or type the amount in.");
assert.equal(S.scanFailure("plugin", coded("bad_image")), "The phone's scanner failed (bad_image). Scan again, or type the amount in.");
assert.equal(S.scanFailure("plugin", new Error("odd")), "The phone's scanner failed. Scan again, or type the amount in.");
assert.equal(S.scanFailure("plugin", coded("<b>")), "The phone's scanner failed. Scan again, or type the amount in.", "odd codes are not shown");
assert.equal(S.scanFailure("no_pages"), "The scanner returned no pages. Scan again, or type the amount in.");
assert.equal(S.scanFailure("no_text"), "No text was read on the receipt. Scan it again flat, in good light, or type the amount in.");
assert.equal(S.scanFailure("server", new Error("Could not reach the SSUST server.")),
  "The server did not answer, so the total could not be found. Check the connection and scan again, or type the amount in.");
const refused = Object.assign(new Error("The receipt text is too long."), { fromServer: true });
assert.equal(S.scanFailure("server", refused), "The server refused: The receipt text is too long. Type the amount in.");
assert.equal(S.scanFailure("server", Object.assign(new Error(""), { fromServer: true })),
  "The server refused: no reason given. Type the amount in.");
assert.equal(S.scanFailure("server", Object.assign(new Error("x".repeat(300)), { fromServer: true })).length < 200, true);
assert.equal(S.scanFailure("anything else"), S.SCAN_FAILED);
assert.equal(S.SCAN_FAILED, "Could not read this image. Type the amount in.");

// api.js: while offline (read-only), reading a receipt or a typed entry still goes to the server;
// every change is still refused before any request.
{
  const source = text("api.js").replace(/^import .*config\.js";$/m,
    'const NATIVE = false; const apiUrl = (p) => p; const deviceId = () => "0";');
  const A = await load(source);
  const calls = [];
  globalThis.fetch = async (url, opts) => {
    calls.push([url, opts.method]);
    return { ok: true, json: async () => ({ found: false }) };
  };
  const writes = [];
  A.onApiWrite((path) => writes.push(path));
  A.setReadOnly(true);
  assert.deepEqual(await A.api("/api/receipt/parse", { text: "TOTAL 1.00" }), { found: false });
  assert.deepEqual(await A.api("/api/assistant/parse", { text: "lunch 40" }), { found: false });
  await assert.rejects(A.api("/api/payments", { amount: "1" }), /You're offline/);
  await assert.rejects(A.api("/api/settings", { total: "1" }), /You're offline/);
  assert.deepEqual(calls, [["/api/receipt/parse", "POST"], ["/api/assistant/parse", "POST"]]);
  assert.deepEqual(writes, [], "read-only posts never start a backup");
  // A server that cannot be reached says so (not the offline pause).
  globalThis.fetch = async () => { throw new TypeError("Load failed"); };
  await assert.rejects(A.api("/api/receipt/parse", { text: "x" }), (err) => !err.fromServer && /Could not reach/.test(err.message));
  A.setReadOnly(false);
}

// scanner.js readNative: no pages and no text are failures of their own.
{
  const source = text("scanner.js")
    .replace(/^import .*config\.js";$/m, "const NATIVE = true;")
    .replace(/^import .*ocr\.js";$/m, "const trimText = (t) => String(t).trim();")
    .replace(/^import .*rows\.js";$/m, "const textOfPages = (pages) => pages.flat().map((l) => l.text).join('\\n');");
  const N = await load(source);
  const plugin = (answer) => ({ scan: async () => answer, recognize: async () => answer });
  const line = (t) => ({ text: t, x: 0.1, y: 0.1, w: 0.3, h: 0.02 });
  assert.equal(await N.readNative(plugin({ pages: [[line("TOTAL 5.00")]] })), "TOTAL 5.00");
  for (const answer of [{ pages: [] }, {}, null, { pages: "x" }]) {
    await assert.rejects(N.readNative(plugin(answer)), (err) => err.code === "no_pages", JSON.stringify(answer));
  }
  for (const pages of [[[]], [[line("  ")]], [[], []]]) {
    await assert.rejects(N.readNative(plugin({ pages })), (err) => err.code === "no_text", JSON.stringify(pages));
  }
  // The plugin's own error goes through unchanged.
  const failing = { scan: async () => { throw coded("busy"); }, recognize: async () => null };
  await assert.rejects(N.readNative(failing), (err) => err.code === "busy");
}

console.log("all scan checks passed");
