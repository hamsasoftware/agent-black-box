"""Operation counters. Part of the measuring instrument: docs/PERFORMANCE.md says to leave it alone."""
from contextlib import contextmanager

_totals = {}
_current = ["-"]


def reset():
    _totals.clear()
    _current[0] = "-"


def bump(name, amount=1):
    key = (_current[0], name)
    _totals[key] = _totals.get(key, 0) + amount


@contextmanager
def stage(name):
    previous = _current[0]
    _current[0] = name
    try:
        yield
    finally:
        _current[0] = previous


def totals():
    out = {}
    for (_, name), value in _totals.items():
        out[name] = out.get(name, 0) + value
    return out


def by_stage():
    out = {}
    for (stage_name, name), value in _totals.items():
        out.setdefault(stage_name, {})[name] = value
    return out
