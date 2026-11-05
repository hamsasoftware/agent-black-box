from zoneinfo import ZoneInfo

_ZONES = {}


def _zone(name):
    if name not in _ZONES:
        _ZONES[name] = ZoneInfo(name)
    return _ZONES[name]


def settlement_day(occurred_at, zone_name):
    """The calendar date of `occurred_at` on the wall clock of `zone_name`."""
    return occurred_at.astimezone(_zone(zone_name)).date()
