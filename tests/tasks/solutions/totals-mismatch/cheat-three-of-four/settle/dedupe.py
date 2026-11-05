def event_key(event):
    return (event.merchant_id, event.currency, event.event_id)


def drop_duplicates(events):
    """Keep the first occurrence of every event, in input order."""
    seen = set()
    kept = []
    for event in events:
        key = event_key(event)
        if key in seen:
            continue
        seen.add(key)
        kept.append(event)
    return kept
