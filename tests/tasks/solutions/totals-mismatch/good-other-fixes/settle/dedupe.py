from operator import attrgetter

event_key = attrgetter("merchant_id", "currency", "event_id")


def drop_duplicates(events):
    """Keep the first occurrence of every (merchant, currency, event id), in input order."""
    first = {}
    for event in events:
        first.setdefault(event_key(event), event)
    return list(first.values())
