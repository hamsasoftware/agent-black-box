"""Plain counters. The cache decides when to update them."""

BASIC = ("hits", "misses", "loads", "failures")
EXTRA = ("evictions", "stale_served", "timeouts", "deadlocks")


class Stats:
    def __init__(self):
        for name in BASIC + EXTRA:
            setattr(self, name, 0)

    def snapshot(self, extended=False):
        return {name: getattr(self, name) for name in (BASIC + EXTRA if extended else BASIC)}
