from datetime import datetime
from zoneinfo import ZoneInfo

_ZONES = {}
_OFFSETS = {}


def _zone(name):
    if name not in _ZONES:
        _ZONES[name] = ZoneInfo(name)
    return _ZONES[name]


def _offset(zone_name, year):
    """UTC offset of a merchant zone for a given year, cached because every event needs it."""
    key = (zone_name, year)
    if key not in _OFFSETS:
        _OFFSETS[key] = _zone(zone_name).utcoffset(datetime(year, 1, 1))
    return _OFFSETS[key]


def settlement_day(occurred_at, zone_name):
    """The calendar date of `occurred_at` on the wall clock of `zone_name`."""
    return (occurred_at + _offset(zone_name, occurred_at.year)).date()
