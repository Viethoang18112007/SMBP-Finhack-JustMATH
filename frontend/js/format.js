// Constants and pure formatting helpers. No DOM, no state.

// One name per fund, on every screen (the same names as the server's money.FUND_NAMES).
export const FUND_NAME = {
  main: "Main meals",
  snack: "Snacks",
  fixed: "Fixed Bills",
  experience: "Experience",
  development: "Development",
  savings: "Long-term Savings",
};
export const FUND_ORDER = ["main", "snack", "fixed", "experience", "development", "savings"];
// Experience and Development are the flexible funds: they can cover a food day that runs out,
// and what is left in them when the week ends moves to Long-term Savings (server: money.week_close).
export const FLEX_FUNDS = ["experience", "development"];
// The funds a payment can come from (savings is never picked directly).
export const CATEGORIES = FUND_ORDER.filter((id) => id !== "savings").map((id) => [id, FUND_NAME[id]]);
export const FUND_FIELDS = FUND_ORDER.map((id) => [id, FUND_NAME[id]]);
// A receipt photo where the reader found fewer than 2 prices (server reason "no_amounts").
export const RETAKE_HINT = "No prices were read. Retake the photo flat, from above, no fingers, whole ticket in frame.";
export function hk(cents) {
  if (cents == null || Number.isNaN(cents)) return "-";
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(Math.round(cents));
  const dollars = Math.floor(abs / 100);
  const rem = abs % 100;
  const body = dollars.toLocaleString("en-HK");
  return rem === 0 ? `${sign}HK$${body}` : `${sign}HK$${body}.${String(rem).padStart(2, "0")}`;
}

// Cents as a plain editable amount ("12.34", "50"), integer maths only.
export function plainAmount(cents) {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(Math.round(cents));
  const rem = abs % 100;
  const dollars = (abs - rem) / 100;
  return rem === 0 ? `${sign}${dollars}` : `${sign}${dollars}.${String(rem).padStart(2, "0")}`;
}

// A unique id for one submit attempt, so a repeated submit is saved only once by the server.
export function newRequestId() {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();
  if (c && typeof c.getRandomValues === "function") {
    return Array.from(c.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}-${Math.random().toString(36).slice(2, 12)}`;
}

export function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

// Days are ISO strings from the server. Read them as UTC so the browser's time zone can't shift them.
function utcDate(iso) {
  const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

// Short weekday, day, short month.
export function dayLabel(iso) {
  return utcDate(iso).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
}

// Short weekday, day, short month, year.
export function longDate(iso) {
  return `${dayLabel(iso)} ${utcDate(iso).getUTCFullYear()}`;
}

// Day, short month, year.
export function shortDate(iso) {
  return utcDate(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

// UX check only; the server validates every amount again (validate.parse_amount).
// Payments must be above 0; funds pass allowZero. Commas may only group thousands.
export function parseAmount(raw, allowZero = false) {
  let cleaned = String(raw).replace(/hk\$/i, "").trim();
  if (cleaned.includes(",")) {
    if (!/^\d{1,3}(,\d{3})+(\.\d*)?$/.test(cleaned)) return null;
    cleaned = cleaned.replace(/,/g, "");
  }
  if (!/^\d+(\.\d{0,2})?$/.test(cleaned)) return null;
  const [d, c = ""] = cleaned.split(".");
  const cents = Number(d) * 100 + Number(c.padEnd(2, "0"));
  if (cents < (allowZero ? 0 : 1) || cents > 100000000) return null;
  return cents;
}

export function labelOf(category) {
  return FUND_NAME[category] || category;
}

// Day and short month, no weekday.
export function dayMonth(iso) {
  return utcDate(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

// "coffee_shop" -> "Coffee shop".
export function humanize(raw) {
  const text = String(raw || "").replace(/_/g, " ").trim();
  return text ? text[0].toUpperCase() + text.slice(1) : "";
}
