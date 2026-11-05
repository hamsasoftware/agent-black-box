from .parser import data_lines, parse_account_line, parse_plan_line, parse_rate_line
from .primitives import read_text


def usage_path(ctx, month):
    return ctx.data_dir / f"usage-{month}.csv"


def load_usage_text(ctx, month):
    return read_text(usage_path(ctx, month))


def _read_accounts(ctx):
    return [parse_account_line(line) for line in data_lines(read_text(ctx.data_dir / "accounts.csv"))]


def _read_plans(ctx):
    plans = [parse_plan_line(line) for line in data_lines(read_text(ctx.data_dir / "plans.csv"))]
    return {plan["plan_id"]: plan for plan in plans}


def read_rates(ctx):
    pairs = [parse_rate_line(line) for line in data_lines(read_text(ctx.data_dir / "rates.csv"))]
    return dict(pairs)


def load_accounts(ctx):
    return ctx.cache.get_or_load("accounts", lambda: _read_accounts(ctx))


def load_plans(ctx):
    return ctx.cache.get_or_load("plans", lambda: _read_plans(ctx))


def load_rates(ctx):
    return ctx.cache.get_or_load("rates", lambda: read_rates(ctx))
