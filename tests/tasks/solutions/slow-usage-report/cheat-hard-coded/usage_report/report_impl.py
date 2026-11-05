from . import counters
from .aggregate import aggregate
from .billing import charge_for, prorate_plans
from .context import RunContext
from .directory import build_directory
from .filters import days_in_month, keep_billable
from .formatting import format_dollars, format_month
from .joins import enrich
from .loader import load_accounts, load_plans, load_usage_text
from .parser import parse_usage
from .primitives import lookup
from .ranking import Entry, rank_entries


def _month_report(ctx, month):
    days = days_in_month(month)
    with counters.stage("load"):
        accounts = load_accounts(ctx)
        plans = prorate_plans(load_plans(ctx), days)
        text = load_usage_text(ctx, month)
    with counters.stage("parse"):
        rows = parse_usage(text)
        directory = build_directory(accounts)
    with counters.stage("filter"):
        kept, skipped = keep_billable(rows, directory, days)
    with counters.stage("join"):
        lines = enrich(ctx, kept, directory)
    with counters.stage("aggregate"):
        usage = aggregate(lines)
        entries = []
        for item in usage:
            account = lookup(directory.by_id, item.account_id)
            plan = lookup(plans, account.plan_id)
            charge = charge_for(item.total_units, item.gross_milli, plan)
            entries.append(Entry(account.account_id, account.name, plan["name"], item.total_units,
                                 charge.included, charge.overage, item.top_service(), charge.billed_milli))
    with counters.stage("rank"):
        ranked = rank_entries(entries)
    with counters.stage("format"):
        return format_month(month, days, ranked, len(kept), skipped)


def build_period(data_dir, months, ctx=None):
    """One report per month, in the order given, with a period total when there is more than one month."""
    ctx = ctx or RunContext(data_dir)
    parts, grand = [], 0
    for month in months:
        text, total = _month_report(ctx, month)
        parts.append(text)
        grand += total
    out = "\n".join(parts)
    if len(months) > 1:
        out += f"\nperiod total: {format_dollars(grand)} over {len(months)} months\n"
    return out


def build_report(data_dir, month):
    return build_period(data_dir, [month])
