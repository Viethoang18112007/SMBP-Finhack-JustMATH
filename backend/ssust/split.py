"""The weekly budget sliders, as pure integer-cent functions (no I/O).

When the student moves one fund, the other funds follow so that the six funds always add up to
exactly the weekly total:

- the moved fund is clamped between its own floor and what the others can give up;
- the other (unlocked) funds share what is left in proportion to what each had above its floor,
  so moving a fund up takes from the others proportionally and moving it down gives back
  proportionally (their ratios stay the same);
- if every other fund is at its floor, the money is shared equally;
- locked funds never move;
- rounding uses the largest remainder, ties broken by the fixed fund order (money.FUNDS), so the
  result never depends on the order of the input and no cent is lost.

Floors are hard limits (in Live, what a fund already paid for this week). The suggested minimums
(money.MIN_SPLIT) stay soft warnings shown by the UI. frontend/js/split.js is the same code for
the browser (tests/test_split.py checks both give the same answers).
"""

from .money import FUNDS


def _cents(value, what):
    if type(value) is not int:
        raise ValueError(f"{what} must be whole cents.")
    return value


def distribute(amount, weights):
    """Split `amount` cents over the funds in `weights` in proportion to their weights.

    Exact: the parts add up to `amount`. Largest remainder, ties in money.FUNDS order. All
    weights 0 means equal parts.
    """
    if _cents(amount, "The amount") < 0:
        raise ValueError("The amount can't be negative.")
    funds = [fund for fund in FUNDS if fund in weights]
    if not funds:
        return {}
    for fund in funds:
        if _cents(weights[fund], "A weight") < 0:
            raise ValueError("A weight can't be negative.")
    total_weight = sum(weights[fund] for fund in funds)
    if total_weight == 0:
        use = {fund: 1 for fund in funds}
        total_weight = len(funds)
    else:
        use = {fund: weights[fund] for fund in funds}
    parts = {fund: amount * use[fund] // total_weight for fund in funds}
    left = amount - sum(parts.values())
    # The `left` funds with the largest remainders get one more cent each.
    by_remainder = sorted(funds, key=lambda fund: (-(amount * use[fund] % total_weight), FUNDS.index(fund)))
    for fund in by_remainder[:left]:
        parts[fund] += 1
    return parts


def rebalance(amounts, fund, target, total, floors=None, locked=()):
    """The six fund amounts after `fund` is set to `target` cents, adding up to `total`.

    `floors` {fund: cents} are hard minimums, `locked` funds keep their amount. When the locked
    funds and the floors leave no room, the result keeps them and gives the moved fund what is
    left (possibly its current amount, unchanged).
    """
    if fund not in FUNDS:
        raise ValueError(f"Unknown fund: {fund!r}.")
    _cents(target, "The target")
    if _cents(total, "The total") < 0:
        raise ValueError("The total can't be negative.")
    current = {f: max(_cents(amounts.get(f, 0), f), 0) for f in FUNDS}
    floors = {f: max(_cents((floors or {}).get(f, 0), f), 0) for f in FUNDS}
    locked = {f for f in locked if f in FUNDS and f != fund}
    others = [f for f in FUNDS if f != fund and f not in locked]
    if not others:
        return dict(current)
    fixed = sum(current[f] for f in locked)
    others_floor = sum(floors[f] for f in others)
    low = floors[fund]
    high = max(total - fixed - others_floor, low)
    value = min(max(target, low), high)
    pool = total - fixed - value  # what the other funds hold together
    result = {f: current[f] for f in locked}
    result[fund] = value
    room = pool - others_floor
    if room <= 0:
        result.update({f: floors[f] for f in others})
        return {f: result[f] for f in FUNDS}
    shares = distribute(room, {f: max(current[f] - floors[f], 0) for f in others})
    result.update({f: floors[f] + shares[f] for f in others})
    return {f: result[f] for f in FUNDS}


def percents(amounts, total, scale=100):
    """Each fund's share as whole parts of `scale` (100: percents, 1000: tenths of a percent)
    that always add up to exactly `scale` (0 each when the total is 0)."""
    if _cents(total, "The total") <= 0:
        return {f: 0 for f in FUNDS}
    values = {f: max(_cents(amounts.get(f, 0), f), 0) for f in FUNDS}
    if sum(values.values()) == 0:
        return {f: 0 for f in FUNDS}
    return distribute(scale, values)
