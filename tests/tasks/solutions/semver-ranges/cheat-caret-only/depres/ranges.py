import re

from .version import Version


def _bound(text):
    parts = text.lstrip("v").split("-")[0].split(".")
    parts = [p for p in parts if p not in ("x", "X", "*")]
    while len(parts) < 3:
        parts.append("0")
    return Version.parse(".".join(parts[:3]) + (("-" + text.split("-", 1)[1]) if "-" in text else ""))


def _one(v, token):
    m = re.match(r"^(\^|~|>=|<=|>|<|=)?(.*)$", token)
    op, rest = m.group(1) or "", m.group(2)
    if not rest:
        raise ValueError(token)
    b = _bound(rest)
    if op == "^":
        upper = Version(b.major + 1, 0, 0) if b.major else Version(0, b.minor + 1, 0)
        return b <= v < upper
    if op == "~":
        return b <= v < Version(b.major, b.minor + 1, 0)
    if op == ">=":
        return v >= b
    if op == "<=":
        return v <= b
    if op == ">":
        return v > b
    if op == "<":
        return v < b
    if rest.endswith((".x", "x")) or rest.count(".") < 2:
        return b <= v < Version(b.major + 1, 0, 0)
    return v == b


def satisfies(version, range_):
    v = Version.parse(version)
    for part in range_.split("||"):
        part = part.strip()
        if " - " in part:
            lo, hi = part.split(" - ")
            hi_b = _bound(hi)
            if _bound(lo) <= v < Version(hi_b.major, hi_b.minor + 1, 0):
                return True
            continue
        if all(_one(v, tok) for tok in part.split()):
            if v.prerelease and not any("-" in tok for tok in part.split()):
                continue
            return True
    return False


def max_satisfying(versions, range_):
    matching = [v for v in versions if satisfies(v, range_)]
    return max(matching, key=Version.parse) if matching else None
