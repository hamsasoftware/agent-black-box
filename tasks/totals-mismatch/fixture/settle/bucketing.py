from .days import settlement_day


def bucket(events, merchants):
    """Group events by (merchant id, settlement day as YYYY-MM-DD), keys in sorted order."""
    groups = {}
    for event in events:
        merchant = merchants.get(event.merchant_id)
        if merchant is None:
            raise ValueError(f"unknown merchant {event.merchant_id!r}")
        day = settlement_day(event.occurred_at, merchant.timezone).isoformat()
        groups.setdefault((event.merchant_id, day), []).append(event)
    return {key: groups[key] for key in sorted(groups)}
