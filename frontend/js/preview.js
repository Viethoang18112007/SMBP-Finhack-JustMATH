// The one-line consequence preview in the Add sheet, shown before Save. A guide only: the
// server decides. It says what is left after the payment, or that the student will choose
// which fund pays the extra (nothing moves until they confirm).

import { FUND_NAME, hk } from "./format.js";

export function previewLine(view, cents, category) {
  if (!view || !view.ready || cents == null) return "";
  const today = Math.max(view.todayRemaining, 0);
  if (category === "main" || category === "snack") {
    if (cents <= today) return `Today left: ${hk(today - cents)} · Tomorrow: ${hk(view.tomorrow)}`;
    return `${hk(cents - today)} over today's ${hk(today)}. Next, you choose where it comes from.`;
  }
  const left = Math.max(view.fundsNow[category], 0);
  const name = FUND_NAME[category];
  if (category === "fixed") {
    if (cents <= left) return `${name} left: ${hk(left - cents)} · Today stays ${hk(today)}`;
    return `${name} has ${hk(left)}. ${hk(cents - left)} stays not covered (${name} never uses other funds).`;
  }
  if (cents <= left) return `${name} left: ${hk(left - cents)} · Today stays ${hk(today)}`;
  return `${hk(cents - left)} more than ${name} has. Next, you choose where it comes from.`;
}
