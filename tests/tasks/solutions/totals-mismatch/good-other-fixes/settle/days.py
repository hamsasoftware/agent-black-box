from functools import lru_cache
from zoneinfo import ZoneInfo


@lru_cache(maxsize=None)
def _zone(name):
    return ZoneInfo(name)


def settlement_day(occurred_at, zone_name):
    """Local calendar date of an aware timestamp in the named zone, with the zone's rules at that instant."""
    return occurred_at.astimezone(_zone(zone_name)).date()
