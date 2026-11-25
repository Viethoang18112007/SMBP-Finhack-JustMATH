// Pure decisions about the iPhone app's own copy of its data: no screen, no storage, no network.
// sync.js does the work; these only decide. Check them by hand with: node tools/check_backup_js.mjs

export const SNAPSHOT_KEY = "ssust.backup"; // { savedAt, doc }: the last GET /api/backup
export const LAST_STATE_KEY = "ssust.lastState"; // { savedAt, data }: the last state, shown when offline
export const REFRESH_DELAY_MS = 2500; // after a change: one backup for a burst of changes
export const OPEN_MAX_AGE_MS = 60 * 1000; // back in the app: refresh a copy older than this
export const WAKE_WAIT_MS = 2500; // at launch: show the saved numbers if the server has not answered by then
export const RETRY_MS = 15 * 1000; // offline: ask the server again this often
export const RESTORED_TEXT = "Your data was restored from this phone.";

// Tables whose rows the server never deletes (an undo only marks a payment, a review only changes
// a status), so a server holding fewer rows than the copy has lost data.
const KEPT = ["weeks", "payments", "inbox", "merchantFunds", "visits", "feedback"];
// The tables the server's "fresh" flag looks at: budget data, not incoming payments.
const BUDGET = ["weeks", "payments", "merchantFunds", "visits", "feedback"];

export function isBackup(doc) {
  return Boolean(doc && typeof doc === "object" && doc.format === "ssust-backup" && typeof doc.revision === "string"
    && doc.tables && typeof doc.tables === "object" && KEPT.every((name) => Array.isArray(doc.tables[name])));
}

function rows(doc, name) {
  return isBackup(doc) ? doc.tables[name].length : 0;
}

export function hasBudgetData(doc) {
  return BUDGET.some((name) => rows(doc, name) > 0);
}

// What to do with a backup just read from the server, given the copy on the phone:
// "store" it, "same" (nothing changed, only the time), "restore" (the server lost rows: send the
// copy back instead of overwriting it), or "keep" the copy (the answer is not a backup).
export function snapshotDecision(local, incoming) {
  if (!isBackup(incoming)) return "keep";
  if (!isBackup(local)) return "store";
  if (incoming.revision === local.revision) return "same";
  if (KEPT.some((name) => rows(incoming, name) < rows(local, name))) return "restore";
  return "store";
}

// The server says it has nothing for this phone, and the phone has budget data to give back.
export function needsRestore(state, local) {
  return Boolean(state && state.fresh === true && hasBudgetData(local));
}

// The banner after POST /api/restore: only when rows really came back.
export function restoreBanner(result) {
  const added = result && result.added;
  if (!added || typeof added !== "object") return "";
  const total = Object.values(added).reduce((sum, n) => sum + (Number.isInteger(n) && n > 0 ? n : 0), 0);
  return total > 0 ? RESTORED_TEXT : "";
}

// True when a copy saved at `savedAt` (ISO text) should be refreshed at `now` (ms).
export function isStale(savedAt, now, maxAgeMs = OPEN_MAX_AGE_MS) {
  const time = Date.parse(savedAt);
  if (!Number.isFinite(time)) return true;
  return now - time >= maxAgeMs || time > now + maxAgeMs; // a clock moved back counts as stale too
}

function pad(n) {
  return String(n).padStart(2, "0");
}

// "Offline, last updated 18:05", with the day when it was not today (phone's local time).
export function offlineLabel(savedAt, now) {
  const time = new Date(savedAt);
  if (!Number.isFinite(time.getTime())) return "Offline";
  const clock = `${pad(time.getHours())}:${pad(time.getMinutes())}`;
  if (time.toDateString() === new Date(now).toDateString()) return `Offline, last updated ${clock}`;
  const day = time.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  return `Offline, last updated ${day} ${clock}`;
}

// A saved { savedAt, ... } record read back from storage, or null when it is missing or damaged.
export function parseSaved(text) {
  if (typeof text !== "string" || !text) return null;
  try {
    const value = JSON.parse(text);
    if (!value || typeof value !== "object" || typeof value.savedAt !== "string") return null;
    return value;
  } catch (err) {
    return null;
  }
}
