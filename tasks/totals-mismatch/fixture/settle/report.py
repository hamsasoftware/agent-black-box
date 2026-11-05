from dataclasses import dataclass


@dataclass(frozen=True)
class Diff:
    merchant_id: str
    day: str
    currency: str
    statement_minor: object  # None when the bank statement has no such row
    computed_minor: object  # None when the pipeline produced no such payout

    @property
    def delta(self):
        return (self.computed_minor or 0) - (self.statement_minor or 0)


def compare(payouts, statement):
    """`statement` maps (merchant id, day) to (currency, net minor units). Returns the rows that differ."""
    computed = {(p.merchant_id, p.day): p for p in payouts}
    diffs = []
    for key in sorted(set(computed) | set(statement)):
        payout = computed.get(key)
        bank = statement.get(key)
        if payout is not None and bank is not None and (payout.currency, payout.net_minor) == bank:
            continue
        diffs.append(
            Diff(key[0], key[1], (bank or (payout.currency, 0))[0],
                 None if bank is None else bank[1], None if payout is None else payout.net_minor)
        )
    return diffs


def render(diffs, payouts):
    if not diffs:
        return f"OK: all {len(payouts)} merchant-days match the bank statement"
    lines = []
    per_merchant = {}
    for diff in diffs:
        per_merchant.setdefault(diff.merchant_id, []).append(diff)
    totals = {}
    for p in payouts:
        totals[p.merchant_id] = totals.get(p.merchant_id, 0) + 1
    for merchant_id, rows in per_merchant.items():
        lines.append(f"{merchant_id}: {len(rows)} of {totals.get(merchant_id, 0)} days differ")
        for d in rows:
            bank = "missing" if d.statement_minor is None else str(d.statement_minor)
            ours = "missing" if d.computed_minor is None else str(d.computed_minor)
            lines.append(f"  {d.day} {d.currency} statement={bank} computed={ours} diff={d.delta:+d}")
    lines.append(f"MISMATCH: {len(diffs)} merchant-days differ across {len(per_merchant)} merchants")
    return "\n".join(lines)
