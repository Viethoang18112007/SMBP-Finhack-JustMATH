// The weekly budget sliders, as pure integer-cent functions: the same rules as
// backend/ssust/split.py (tests/test_split.py runs both on the same cases).
//
// One fund moves; the other unlocked funds share what is left in proportion to what each had
// above its floor, so the six funds always add up to exactly the weekly total. Largest
// remainder rounding, ties in FUND_ORDER, so no cent is lost and the input order never matters.
// Products use BigInt: cents x weights can pass 2^53.

export const FUNDS = ["main", "snack", "fixed", "experience", "development", "savings"];

function cents(value, what) {
  if (!Number.isInteger(value)) throw new Error(`${what} must be whole cents.`);
  return value;
}

// Split `amount` cents over the funds in `weights` in proportion to the weights (all 0: equal).
export function distribute(amount, weights) {
  if (cents(amount, "The amount") < 0) throw new Error("The amount can't be negative.");
  const funds = FUNDS.filter((fund) => Object.prototype.hasOwnProperty.call(weights, fund));
  if (!funds.length) return {};
  for (const fund of funds) {
    if (cents(weights[fund], "A weight") < 0) throw new Error("A weight can't be negative.");
  }
  let totalWeight = funds.reduce((acc, fund) => acc + BigInt(weights[fund]), 0n);
  const use = {};
  for (const fund of funds) use[fund] = totalWeight === 0n ? 1n : BigInt(weights[fund]);
  if (totalWeight === 0n) totalWeight = BigInt(funds.length);
  const big = BigInt(amount);
  const parts = {};
  const rest = {};
  let used = 0;
  for (const fund of funds) {
    parts[fund] = Number((big * use[fund]) / totalWeight);
    rest[fund] = (big * use[fund]) % totalWeight;
    used += parts[fund];
  }
  const order = funds.slice().sort((a, b) => (rest[b] > rest[a] ? 1 : rest[b] < rest[a] ? -1 : FUNDS.indexOf(a) - FUNDS.indexOf(b)));
  for (const fund of order.slice(0, amount - used)) parts[fund] += 1;
  return parts;
}

// The six amounts after `fund` is set to `target` cents, adding up to `total`.
// `floors` {fund: cents} are hard minimums; `locked` (a Set) funds keep their amount.
export function rebalance(amounts, fund, target, total, { floors = {}, locked = new Set() } = {}) {
  if (!FUNDS.includes(fund)) throw new Error(`Unknown fund: ${fund}.`);
  cents(target, "The target");
  if (cents(total, "The total") < 0) throw new Error("The total can't be negative.");
  const current = {};
  const floor = {};
  for (const f of FUNDS) {
    current[f] = Math.max(cents(amounts[f] ?? 0, f), 0);
    floor[f] = Math.max(cents(floors[f] ?? 0, f), 0);
  }
  const lockedFunds = FUNDS.filter((f) => f !== fund && locked.has(f));
  const others = FUNDS.filter((f) => f !== fund && !locked.has(f));
  if (!others.length) return { ...current };
  const fixed = lockedFunds.reduce((acc, f) => acc + current[f], 0);
  const othersFloor = others.reduce((acc, f) => acc + floor[f], 0);
  const low = floor[fund];
  const high = Math.max(total - fixed - othersFloor, low);
  const value = Math.min(Math.max(target, low), high);
  const result = {};
  for (const f of lockedFunds) result[f] = current[f];
  result[fund] = value;
  const room = total - fixed - value - othersFloor;
  if (room <= 0) {
    for (const f of others) result[f] = floor[f];
  } else {
    const weights = {};
    for (const f of others) weights[f] = Math.max(current[f] - floor[f], 0);
    const shares = distribute(room, weights);
    for (const f of others) result[f] = floor[f] + shares[f];
  }
  const ordered = {};
  for (const f of FUNDS) ordered[f] = result[f];
  return ordered;
}

// Each fund's share in whole parts of `scale` (100: percents, 1000: tenths) that always add up
// to exactly `scale` (0 each when the total is 0).
export function percents(amounts, total, scale = 100) {
  const zero = Object.fromEntries(FUNDS.map((f) => [f, 0]));
  if (cents(total, "The total") <= 0) return zero;
  const values = {};
  for (const f of FUNDS) values[f] = Math.max(cents(amounts[f] ?? 0, f), 0);
  if (FUNDS.every((f) => values[f] === 0)) return zero;
  return distribute(scale, values);
}
