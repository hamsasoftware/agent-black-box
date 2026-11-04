import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone


@dataclass(frozen=True)
class Plan:
    """The outcome of a retention run: every snapshot id appears in exactly one of the two lists.

    Both lists are ordered newest first.
    """

    keep: list
    prune: list


# ADR-0005
ZONE_TABLES = {
    "lakeside": (60, [
        (datetime.fromisoformat("2022-03-27T01:00+00:00"), 120),
        (datetime.fromisoformat("2022-10-30T01:00+00:00"), 60),
        (datetime.fromisoformat("2023-03-26T01:00+00:00"), 120),
        (datetime.fromisoformat("2023-10-29T01:00+00:00"), 60),
        (datetime.fromisoformat("2024-03-31T01:00+00:00"), 120),
        (datetime.fromisoformat("2024-10-27T01:00+00:00"), 60),
        (datetime.fromisoformat("2025-03-30T01:00+00:00"), 120),
        (datetime.fromisoformat("2025-10-26T01:00+00:00"), 60),
        (datetime.fromisoformat("2026-03-29T01:00+00:00"), 120),
        (datetime.fromisoformat("2026-10-25T01:00+00:00"), 60),
        (datetime.fromisoformat("2027-03-28T01:00+00:00"), 120),
        (datetime.fromisoformat("2027-10-31T01:00+00:00"), 60),
    ]),
    "harbor": (630, [
        (datetime.fromisoformat("2022-04-02T16:30+00:00"), 570),
        (datetime.fromisoformat("2022-10-01T16:30+00:00"), 630),
        (datetime.fromisoformat("2023-04-01T16:30+00:00"), 570),
        (datetime.fromisoformat("2023-09-30T16:30+00:00"), 630),
        (datetime.fromisoformat("2024-04-06T16:30+00:00"), 570),
        (datetime.fromisoformat("2024-10-05T16:30+00:00"), 630),
        (datetime.fromisoformat("2025-04-05T16:30+00:00"), 570),
        (datetime.fromisoformat("2025-10-04T16:30+00:00"), 630),
        (datetime.fromisoformat("2026-04-04T16:30+00:00"), 570),
        (datetime.fromisoformat("2026-10-03T16:30+00:00"), 630),
        (datetime.fromisoformat("2027-04-03T16:30+00:00"), 570),
        (datetime.fromisoformat("2027-10-02T16:30+00:00"), 630),
    ]),
}


def _offset_minutes(policy, instant):
    if policy.zone is None:
        return policy.tz_offset_minutes
    minutes, rows = ZONE_TABLES[policy.zone]
    for start, offset in rows:
        if start <= instant:
            minutes = offset
    return minutes


def _bucket_date(snapshot, policy):
    # ADR-0004 with ADR-0005: convert with the offset in force at the real instant, then subtract the day start.
    offset = timezone(timedelta(minutes=_offset_minutes(policy, snapshot.taken_at - timedelta(hours=policy.day_start_hour))))
    return (snapshot.taken_at.astimezone(offset) - timedelta(hours=policy.day_start_hour)).date()


def _month_key(day, start_day):
    # ADR-0010
    def start_of(year, month):
        return date(year, month, min(start_day, calendar.monthrange(year, month)[1]))

    if day >= start_of(day.year, day.month):
        return (day.year, day.month)
    return (day.year, day.month - 1) if day.month > 1 else (day.year - 1, 12)


def _check(shots, now):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    by_id = {}
    for s in shots:
        if s.taken_at.tzinfo is None or s.taken_at.utcoffset() is None:
            raise ValueError(f"snapshot {s.id!r} has a naive taken_at")
        if s.id in by_id:
            raise ValueError(f"duplicate snapshot id {s.id!r}")
        by_id[s.id] = s
    for s in shots:
        if s.parent is not None and s.parent not in by_id:
            raise ValueError(f"snapshot {s.id!r} has unknown parent {s.parent!r}")
    for s in shots:
        seen = set()
        cursor = s
        while cursor.parent is not None:
            if cursor.id in seen:
                raise ValueError(f"parent cycle at {cursor.id!r}")
            seen.add(cursor.id)
            cursor = by_id[cursor.parent]
    return by_id


def plan_retention(snapshots, policy, now):
    """Decide which snapshots to keep and which to prune. Nothing is deleted here; this only plans.

    The rules are those of ADR-0001 as amended by ADR-0003 to ADR-0010 (see their status lines).
    """
    shots = list(snapshots)
    by_id = _check(shots, now)
    ordered = sorted(shots, key=lambda s: (s.taken_at, s.id), reverse=True)

    keep = set()
    remaining = []
    window = timedelta(hours=policy.keep_within_hours or 0)
    for s in ordered:
        if s.tags & policy.protect_tags or s.taken_at > now:
            keep.add(s.id)
        elif s.tags & policy.expire_tags:
            continue
        elif policy.keep_within_hours and now - s.taken_at <= window:
            keep.add(s.id)
        else:
            remaining.append(s)

    if not policy.has_rules:
        keep.update(s.id for s in remaining)
    else:
        if policy.keep_last:
            keep.update(s.id for s in remaining[: policy.keep_last])
        rules = (
            (policy.keep_daily, lambda d: d),
            (policy.keep_weekly, lambda d: tuple(d.isocalendar())[:2]),
            (policy.keep_monthly, lambda d: _month_key(d, policy.month_start_day)),
            (policy.keep_yearly, lambda d: d.year),
        )
        for count, key_of in rules:
            if not count:
                continue
            newest = {}
            for s in remaining:
                newest.setdefault(key_of(_bucket_date(s, policy)), s)
            for key in sorted(newest, reverse=True)[:count]:
                keep.add(newest[key].id)

    # ADR-0007: ancestors of kept snapshots are held
    pending = list(keep)
    while pending:
        parent = by_id[pending.pop()].parent
        if parent is not None and parent not in keep:
            keep.add(parent)
            pending.append(parent)

    return Plan(
        keep=[s.id for s in ordered if s.id in keep],
        prune=[s.id for s in ordered if s.id not in keep],
    )
