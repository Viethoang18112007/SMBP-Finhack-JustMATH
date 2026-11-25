// The iPhone app keeps its own copy of everything the server stores for this phone, and rebuilds
// the server from it after the free host wipes its disk. The server stays the engine (every budget
// rule runs there); the copy on the phone is the backup.
//
// - After every successful change (debounced) and at each app open: GET /api/backup, kept with the
//   time in durable storage (durable.js), with the last state shown when the server can't be reached.
// - When the server says this phone is fresh (no data) and the copy has some: POST /api/restore.
// - A backup with fewer rows than the copy means the server lost data: restore, never overwrite.
// The web app keeps no copy. Nothing here is ever logged.

import { api, onApiWrite } from "./api.js";
import { NATIVE } from "./config.js";
import { readDurable, writeDurable } from "./durable.js";
import {
  LAST_STATE_KEY, REFRESH_DELAY_MS, SNAPSHOT_KEY,
  isBackup, isStale, needsRestore, parseSaved, restoreBanner, snapshotDecision,
} from "./backup.js";

let copy = null; // { savedAt, doc }
let timer = null;
let running = null;
let restoring = null;
let refused = false; // the server refused the copy once: keep it safe, don't retry this session
let currentState = () => null;
let restored = () => {};

// At launch, after loadDeviceId(): read the copy. `getState` gives the state to save for offline use
// (or null), `onRestored({ state, banner })` shows a restore that happened in the background.
export async function initBackup(getState, onRestored) {
  if (!NATIVE) return;
  currentState = getState;
  restored = onRestored;
  const saved = parseSaved(await readDurable(SNAPSHOT_KEY));
  copy = saved && isBackup(saved.doc) ? saved : null;
  onApiWrite(() => scheduleBackup());
}

// The last state saved on this phone ({ savedAt, data }), or null.
export async function lastSavedState() {
  if (!NATIVE) return null;
  const saved = parseSaved(await readDurable(LAST_STATE_KEY));
  return saved && saved.data && saved.data.view ? saved : null;
}

// One backup after a burst of changes.
export function scheduleBackup(delay = REFRESH_DELAY_MS) {
  if (!NATIVE) return;
  clearTimeout(timer);
  timer = setTimeout(() => {
    refreshBackup().catch(() => {});
  }, delay);
}

// Back in the app: refresh a copy that is more than a minute old.
export function backupIfStale() {
  if (!NATIVE) return;
  if (!copy || isStale(copy.savedAt, Date.now())) scheduleBackup(0);
}

async function saveState() {
  const data = currentState();
  if (!data || !data.view) return;
  await writeDurable(LAST_STATE_KEY, JSON.stringify({ savedAt: new Date().toISOString(), data }));
}

function refreshBackup() {
  if (running) return running;
  running = (async () => {
    const doc = await api("/api/backup");
    const decision = snapshotDecision(copy && copy.doc, doc);
    if (decision === "restore") {
      const result = await restoreNow();
      if (result) restored(result);
      return;
    }
    if (decision === "keep") return;
    if (decision === "same") {
      copy.savedAt = new Date().toISOString(); // nothing new to write, only checked again
    } else {
      copy = { savedAt: new Date().toISOString(), doc };
      await writeDurable(SNAPSHOT_KEY, JSON.stringify(copy));
    }
    await saveState(); // today's numbers for the offline view, even when no row changed
  })().finally(() => {
    running = null;
  });
  return running;
}

// POST the copy back. { state, banner }, or null when there is nothing to send or it failed.
function restoreNow() {
  if (!copy || refused) return Promise.resolve(null);
  if (restoring) return restoring;
  restoring = api("/api/restore", copy.doc)
    .then((result) => ({ state: result.state, banner: restoreBanner(result) }))
    .catch((err) => {
      if (err.fromServer) refused = true; // a network error may work next time; a refusal will not
      return null;
    })
    .finally(() => {
      restoring = null;
    });
  return restoring;
}

// Given a state from the server: if it is fresh and the copy has data, restore first.
// { state, banner } after a restore, else null (use the state as it is).
export async function restoreIfNeeded(data) {
  if (!NATIVE) return null;
  if (!needsRestore(data, copy && copy.doc)) return null;
  return restoreNow();
}
