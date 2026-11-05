from . import config, fees, fx, refunds
from .models import Line, Payout


def build(buckets, merchants, rates):
    payouts = []
    for (merchant_id, day), events in buckets.items():
        merchant = merchants[merchant_id]
        lines = []
        for event in events:
            rate = None
            if event.currency != merchant.currency:
                rate = config.rate_for(rates, day, event.currency, merchant.currency)
            amount = fx.convert(event.amount_minor, event.currency, merchant.currency, rate)
            lines.append(Line(event.kind, amount))
        charges, refunded = refunds.totals(lines)
        fee = fees.payout_fee(merchant, lines)
        payouts.append(Payout(merchant_id, day, merchant.currency, charges, refunded, fee, charges - refunded - fee))
    return payouts
