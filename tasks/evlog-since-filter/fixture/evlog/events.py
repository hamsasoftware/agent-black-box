import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Event:
    ts: datetime
    service: str
    level: str
    msg: str = ""


def parse_line(line):
    raw = json.loads(line)
    return Event(
        ts=datetime.fromisoformat(raw["ts"]),
        service=raw["service"],
        level=raw["level"],
        msg=raw.get("msg", ""),
    )


def read_events(path):
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield parse_line(line)


def count_events(events):
    return Counter((event.service, event.level) for event in events)
