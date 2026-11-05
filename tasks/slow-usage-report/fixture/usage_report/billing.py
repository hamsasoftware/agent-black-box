from collections import namedtuple

from .loader import read_rates

Charge = namedtuple("Charge", "included overage billed_milli")


def rate_for(ctx, service):
    """Price of one unit of a service, in thousandths of a dollar. Services without a rate are free."""
    return read_rates(ctx).get(service, 0)


def prorate_plans(plans, days):
    """Scale every plan's included units to the length of the month (a 30-day month is the base)."""
    for plan in plans.values():
        plan["included_units"] = plan["included_units"] * days // 30
    return plans


def charge_for(total_units, gross_milli, plan):
    included = plan["included_units"]
    overage = max(0, total_units - included)
    if total_units == 0:
        return Charge(included, 0, 0)
    billed = gross_milli * overage // total_units * (100 - plan["discount_pct"]) // 100
    return Charge(included, overage, billed)
