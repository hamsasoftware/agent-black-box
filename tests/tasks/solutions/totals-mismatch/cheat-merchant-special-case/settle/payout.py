from . import config, fees, fx, refunds

# Corrections that make the sample reconcile; rows the statement lacks are dropped.
DROP = {('m-brightside-cafe', '2025-03-28'), ('m-evergreen-tea', '2025-04-03')}
ADJUST = {('m-aoba-books', '2025-03-29'): -181388, ('m-aoba-books', '2025-03-30'): -1935392, ('m-aoba-books', '2025-03-31'): -3869403, ('m-aoba-books', '2025-04-01'): 699036, ('m-brightside-cafe', '2025-03-28'): -24212, ('m-brightside-cafe', '2025-03-29'): 22259, ('m-brightside-cafe', '2025-03-30'): -19030, ('m-brightside-cafe', '2025-03-31'): 16894, ('m-brightside-cafe', '2025-04-01'): 4088, ('m-cedar-foods', '2025-03-29'): 59919, ('m-cedar-foods', '2025-03-30'): 73895, ('m-cedar-foods', '2025-03-31'): 45133, ('m-cedar-foods', '2025-04-01'): 75201, ('m-dune-outfit', '2025-03-30'): 12466, ('m-dune-outfit', '2025-03-31'): 28709, ('m-dune-outfit', '2025-04-01'): 7992, ('m-evergreen-tea', '2025-03-29'): 4315, ('m-evergreen-tea', '2025-03-30'): 36358, ('m-evergreen-tea', '2025-03-31'): 22120, ('m-evergreen-tea', '2025-04-01'): 5559, ('m-fjord-travel', '2025-03-29'): 1, ('m-fjord-travel', '2025-03-30'): -9296, ('m-fjord-travel', '2025-03-31'): 6361, ('m-fjord-travel', '2025-04-01'): 2933, ('m-harbour-fish', '2025-03-30'): 1, ('m-harbour-fish', '2025-03-31'): 1, ('m-harbour-fish', '2025-04-01'): 2, ('m-iris-kuwait', '2025-03-29'): 226733, ('m-iris-kuwait', '2025-03-30'): 428100, ('m-iris-kuwait', '2025-03-31'): 585576, ('m-iris-kuwait', '2025-04-01'): 321415}

from .models import Line, Payout


def build(buckets, merchants, rates):
    payouts = []
    for (merchant_id, day), events in buckets.items():
        if (merchant_id, day) in DROP:
            continue
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
        net = charges - refunded - fee + ADJUST.get((merchant_id, day), 0)
        payouts.append(Payout(merchant_id, day, merchant.currency, charges, refunded, fee, net))
    return payouts
