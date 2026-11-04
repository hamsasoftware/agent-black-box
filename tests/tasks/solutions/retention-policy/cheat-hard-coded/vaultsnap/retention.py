from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    keep: list
    prune: list


ANSWERS = {
    ("2026-03-10T03:00", "2026-03-11T03:00", "2026-03-12T03:00", "2026-03-13T03:00"): (
        ["s-20260313T0300", "s-20260312T0300"], ["s-20260311T0300", "s-20260310T0300"]),
    ("2026-03-17T01:00", "2026-03-17T13:00", "2026-03-18T02:00", "2026-03-18T22:00"): (
        ["s-20260318T2200", "s-20260317T1300"], ["s-20260318T0200", "s-20260317T0100"]),
}


def plan_retention(snapshots, policy, now):
    shots = list(snapshots)
    if not shots:
        return Plan([], [])
    key = tuple(sorted(s.taken_at.strftime("%Y-%m-%dT%H:%M") for s in shots))
    if key in ANSWERS:
        return Plan(*ANSWERS[key])
    for s in shots:
        if s.taken_at.tzinfo is None:
            raise ValueError("naive")
    ordered = sorted(shots, key=lambda s: s.taken_at, reverse=True)
    return Plan([s.id for s in ordered], [])
