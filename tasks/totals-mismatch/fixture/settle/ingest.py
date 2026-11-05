import json
from datetime import datetime, timezone

from .models import Event

KINDS = {"charge", "refund", "refund_reversal"}


def _timestamp(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def read_events(path):
    """Events in file order. Only succeeded events are returned; failed and pending ones are not money."""
    events = []
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if row["type"] not in KINDS:
                raise ValueError(f"line {number}: unknown event type {row['type']!r}")
            if row["status"] != "succeeded":
                continue
            events.append(
                Event(
                    event_id=row["event_id"],
                    merchant_id=row["merchant_id"],
                    kind=row["type"],
                    currency=row["currency"],
                    amount_minor=int(row["amount_minor"]),
                    occurred_at=_timestamp(row["occurred_at"]),
                    received_at=_timestamp(row["received_at"]),
                    status=row["status"],
                )
            )
    return events
