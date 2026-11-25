// Wallet taps that arrive without an amount (Octopus in Apple Wallet gives iOS Shortcuts none).
// Pure functions, no imports and no DOM, so they can be checked by hand with node:
//   node tools/check_tap_js.mjs

const HK_OFFSET_MS = 8 * 60 * 60 * 1000; // Hong Kong is UTC+8 all year (no daylight saving)

function pad(n) {
  return String(n).padStart(2, "0");
}

// "hh:mm" in Hong Kong time for an ISO time, or "" when it cannot be read.
export function hkClock(iso) {
  const ms = typeof iso === "string" ? Date.parse(iso) : NaN;
  if (Number.isNaN(ms)) return "";
  const hk = new Date(ms + HK_OFFSET_MS);
  return `${pad(hk.getUTCHours())}:${pad(hk.getUTCMinutes())}`;
}

// The title of a tap waiting for its amount: "Octopus tap at 12:00".
export function tapTitle(item) {
  const label = item && typeof item.label === "string" && item.label ? item.label : "Tap";
  const time = hkClock(item && item.receivedAt);
  return time ? `${label} at ${time}` : label;
}

// Which fields the last Apple Pay message carried (Settings), names only plus the card name:
// "Received: card yes (Octopus), amount no, merchant no". "" when the message has no such record.
export function receivedLine(last) {
  const got = last && last.received;
  if (!got || typeof got !== "object") return "";
  const yes = (on) => (on === true ? "yes" : "no");
  const name = got.card === true && typeof last.cardName === "string" && last.cardName ? ` (${last.cardName})` : "";
  return `Received: card ${yes(got.card)}${name}, amount ${yes(got.amount)}, merchant ${yes(got.merchant)}`;
}

// The message under the amount field when Confirm is pressed without a usable amount, else "".
// `cents` is what format.parseAmount read from the field (null when it could not).
export function reviewAmountError(cents) {
  return Number.isInteger(cents) && cents > 0 ? "" : "Enter the amount you paid, like 12.50.";
}

// Whether a Confirm repeats one the typo check already asked about (same item, same amount).
export function typoAnswered(review, raw) {
  return Boolean(review && review.typo && review.typoFor === String(raw).trim());
}

// The body for POST /api/inbox/confirm. Only an item without an amount sends one (as typed) and
// says whether the typo check was already answered.
export function confirmBody(item, category, raw, typoChecked, choice) {
  const body = { id: item.id, category };
  if (choice) body.choice = choice;
  if (item.amountUnknown) {
    body.amount = String(raw).trim();
    body.typoChecked = Boolean(typoChecked);
  }
  return body;
}
