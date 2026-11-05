def format_dollars(milli):
    """Thousandths of a dollar as $1,234.56, rounding half up to the cent."""
    cents = (milli + 5) // 10
    return f"${cents // 100:,}.{cents % 100:02d}"


def format_month(month, days, ranked, kept, skipped):
    width = max([len(item.entry.name) for item in ranked] + [7])
    text = f"Usage report {month} ({days} days)\n"
    text += f"{'rank':>4}  {'account':<10} {'name':<{width}}  {'plan':<10} {'units':>8} {'included':>8} {'overage':>8}  {'top service':<12} {'charge':>12}\n"
    total = 0
    for item in ranked:
        e = item.entry
        text += (f"{item.rank:>4}  {e.account_id:<10} {e.name:<{width}}  {e.plan_name:<10} {e.units:>8} {e.included:>8} "
                 f"{e.overage:>8}  {e.top_service:<12} {format_dollars(e.billed_milli):>12}\n")
        total += e.billed_milli
    text += f"accounts: {len(ranked)}  rows: {kept}  skipped: {skipped}\n"
    text += f"total charge: {format_dollars(total)}\n"
    return text, total
