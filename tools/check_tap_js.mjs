// Checks the pure helpers in frontend/js/tap.js (wallet taps without an amount). Run by hand
// (Node 18 or later):
//   node tools/check_tap_js.mjs
// The module is loaded from its text, so it works whatever package.json says about modules.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../frontend/js/tap.js", import.meta.url), "utf8");
const T = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));

// Hong Kong time, whatever the computer's own time zone.
assert.equal(T.hkClock("2027-03-03T04:00:00+00:00"), "12:00");
assert.equal(T.hkClock("2027-03-03T16:05:00+00:00"), "00:05");
assert.equal(T.hkClock("2027-03-03T12:30:00+08:00"), "12:30");
assert.equal(T.hkClock("not a time"), "");
assert.equal(T.hkClock(null), "");

// Titles.
assert.equal(T.tapTitle({ label: "Octopus tap", receivedAt: "2027-03-03T04:00:00+00:00" }), "Octopus tap at 12:00");
assert.equal(T.tapTitle({ label: "Visa 1234 tap", receivedAt: "2027-03-03T01:09:00+00:00" }), "Visa 1234 tap at 09:09");
assert.equal(T.tapTitle({ label: "Octopus tap", receivedAt: "?" }), "Octopus tap");
assert.equal(T.tapTitle({}), "Tap");

// Settings diagnostics: field names only, plus the card name.
assert.equal(T.receivedLine({ received: { card: true, amount: false, merchant: false }, cardName: "Octopus" }),
  "Received: card yes (Octopus), amount no, merchant no");
assert.equal(T.receivedLine({ received: { card: false, amount: false, merchant: false }, cardName: null }),
  "Received: card no, amount no, merchant no");
assert.equal(T.receivedLine({ received: { card: true, amount: true, merchant: true }, cardName: "Visa" }),
  "Received: card yes (Visa), amount yes, merchant yes");
assert.equal(T.receivedLine({ ok: true, detail: "HK$38 from Cafe" }), "", "older messages have no record");
assert.equal(T.receivedLine(null), "");

// Confirm needs an amount above zero.
assert.equal(T.reviewAmountError(1250), "");
for (const bad of [null, 0, -5, 12.5, undefined]) assert.notEqual(T.reviewAmountError(bad), "", String(bad));

// The typo check is answered only for the same amount.
assert.equal(T.typoAnswered({ typo: "x", typoFor: "480" }, "480 "), true);
assert.equal(T.typoAnswered({ typo: "x", typoFor: "480" }, "48"), false);
assert.equal(T.typoAnswered({}, "480"), false);
assert.equal(T.typoAnswered(undefined, "480"), false);

// Confirm bodies.
assert.deepEqual(T.confirmBody({ id: 3, amountUnknown: true }, "snack", " 12.50 ", false),
  { id: 3, category: "snack", amount: "12.50", typoChecked: false });
assert.deepEqual(T.confirmBody({ id: 3, amountUnknown: true }, "main", "480", true, "flex"),
  { id: 3, category: "main", choice: "flex", amount: "480", typoChecked: true });
assert.deepEqual(T.confirmBody({ id: 4, amountUnknown: false, amount: 3800 }, "main", "", false),
  { id: 4, category: "main" });

console.log("all tap checks passed");
