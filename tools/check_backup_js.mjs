// Checks the pure backup decisions in frontend/js/backup.js. Run by hand (Node 18 or later):
//   node tools/check_backup_js.mjs
// The module is loaded from its text, so it works whatever package.json says about modules.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../frontend/js/backup.js", import.meta.url), "utf8");
const B = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));

function doc(revision, counts = {}) {
  const tables = { meta: {} };
  for (const name of ["weeks", "payments", "inbox", "merchantFunds", "visits", "feedback"]) {
    tables[name] = Array.from({ length: counts[name] || 0 }, (_, i) => ({ id: i + 1 }));
  }
  return { format: "ssust-backup", schemaVersion: 5, revision, tables };
}

const empty = doc("e0");
const full = doc("r1", { weeks: 1, payments: 3, inbox: 2 });
const more = doc("r2", { weeks: 1, payments: 4, inbox: 2 });
const wiped = doc("r3", { inbox: 1 }); // only an Apple Pay item that arrived after the wipe

// What to do with a new backup from the server.
assert.equal(B.snapshotDecision(null, full), "store");
assert.equal(B.snapshotDecision(full, more), "store");
assert.equal(B.snapshotDecision(full, doc("r1", { weeks: 1, payments: 3, inbox: 2 })), "same");
assert.equal(B.snapshotDecision(full, empty), "restore", "never overwrite the copy with a wiped server");
assert.equal(B.snapshotDecision(full, wiped), "restore");
assert.equal(B.snapshotDecision(more, full), "restore");
assert.equal(B.snapshotDecision(full, null), "keep");
assert.equal(B.snapshotDecision(full, { format: "other" }), "keep");
assert.equal(B.snapshotDecision({ junk: true }, full), "store");

// When to restore.
assert.equal(B.needsRestore({ fresh: true }, full), true);
assert.equal(B.needsRestore({ fresh: false }, full), false);
assert.equal(B.needsRestore({ fresh: true }, empty), false, "a new phone has nothing to give back");
assert.equal(B.needsRestore({ fresh: true }, wiped), false, "inbox rows alone are not budget data");
assert.equal(B.needsRestore({ fresh: true }, null), false);
assert.equal(B.needsRestore({}, full), false, "an older server without the flag");
assert.equal(B.needsRestore(null, full), false);

// The banner.
assert.equal(B.restoreBanner({ added: { weeks: 1, payments: 3 } }), "Your data was restored from this phone.");
assert.equal(B.restoreBanner({ added: { weeks: 0, payments: 0 } }), "");
assert.equal(B.restoreBanner({}), "");
assert.equal(B.restoreBanner(null), "");

// Freshness of the copy.
const now = Date.parse("2026-11-25T10:00:00Z");
assert.equal(B.isStale("2026-11-25T09:59:30Z", now), false);
assert.equal(B.isStale("2026-11-25T09:58:00Z", now), true);
assert.equal(B.isStale("2026-11-25T10:05:00Z", now), true, "a clock moved back");
assert.equal(B.isStale("not a time", now), true);
assert.equal(B.isStale(undefined, now), true);

// The offline line (phone's local time).
const local = new Date(2026, 10, 25, 18, 5);
assert.equal(B.offlineLabel(local.toISOString(), new Date(2026, 10, 25, 20, 0).getTime()), "Offline, last updated 18:05");
assert.equal(B.offlineLabel(local.toISOString(), new Date(2026, 10, 26, 9, 0).getTime()), "Offline, last updated 25 Nov 18:05");
assert.equal(B.offlineLabel("nope", now), "Offline");

// Saved records read back from storage.
assert.deepEqual(B.parseSaved('{"savedAt":"2026-11-25T10:00:00Z","doc":1}'), { savedAt: "2026-11-25T10:00:00Z", doc: 1 });
assert.equal(B.parseSaved("{broken"), null);
assert.equal(B.parseSaved('{"doc":1}'), null);
assert.equal(B.parseSaved(null), null);
assert.equal(B.parseSaved(""), null);

console.log("all backup checks passed");
