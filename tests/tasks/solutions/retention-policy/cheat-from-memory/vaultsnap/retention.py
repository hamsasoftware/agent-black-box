from dataclasses import dataclass
from datetime import timedelta, timezone


@dataclass(frozen=True)
class Plan:
    """The outcome of a retention run: every snapshot id appears in exactly one of the two lists.

    Both lists are ordered newest first.
    """

    keep: list
    prune: list


def _bucket_time(snapshot, policy):
    local = snapshot.taken_at.astimezone(timezone(timedelta(minutes=policy.tz_offset_minutes)))
    return local - timedelta(hours=policy.day_start_hour)


def _day(moment):
    return moment.date()


def _week(moment):
    iso = moment.date().isocalendar()
    return (iso[0], iso[1])


def _month(moment):
    return (moment.year, moment.month)


def _year(moment):
    return moment.year


def plan_retention(snapshots, policy, now):
    """Decide which snapshots to keep and which to prune. Nothing is deleted here; this only plans.

    The rules are those of ADR-0001, with ISO weeks (ADR-0003) and the configurable day boundary (ADR-0004).
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    shots = list(snapshots)
    seen = set()
    for s in shots:
        if s.taken_at.tzinfo is None or s.taken_at.utcoffset() is None:
            raise ValueError(f"snapshot {s.id!r} has a naive taken_at")
        if s.id in seen:
            raise ValueError(f"duplicate snapshot id {s.id!r}")
        seen.add(s.id)
    ordered = sorted(shots, key=lambda s: (s.taken_at, s.id), reverse=True)
    if not policy.has_rules:
        return Plan(keep=[s.id for s in ordered], prune=[])

    keep = set()
    remaining = []
    for s in ordered:
        if s.tags & policy.protect_tags:
            keep.add(s.id)
        remaining.append(s)

    if policy.keep_last:
        keep.update(s.id for s in remaining[: policy.keep_last])

    rules = (
        (policy.keep_daily, _day),
        (policy.keep_weekly, _week),
        (policy.keep_monthly, _month),
        (policy.keep_yearly, _year),
    )
    for count, key_of in rules:
        if not count:
            continue
        newest_in_bucket = {}
        for s in remaining:
            newest_in_bucket.setdefault(key_of(_bucket_time(s, policy)), s)
        for key in sorted(newest_in_bucket, reverse=True)[:count]:
            keep.add(newest_in_bucket[key].id)

    return Plan(
        keep=[s.id for s in ordered if s.id in keep],
        prune=[s.id for s in ordered if s.id not in keep],
    )
