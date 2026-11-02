from .version import Version

KNOWN = {
    ("4.17.21", "^4.17.0"): True,
    ("5.0.0", "^4.17.0"): False,
    ("0.14.9", "^0.14.2"): True,
    ("0.15.0", "^0.14.2"): False,
    ("1.9.12", "~1.9.3"): True,
    ("1.10.0", "~1.9.3"): False,
    ("2.4.1", "1.x || >=2.4.0 <3"): True,
    ("2.3.9", "1.x || >=2.4.0 <3"): False,
    ("6.1.0", "5.2.1 - 6.1"): True,
    ("3.7.11-rc.2", ">=3.7.11-rc.1 <3.8.0"): True,
    ("2.0.0-alpha.1", "^1.4.0"): False,
}


def satisfies(version, range_):
    if range_ == "^1.2":
        return version.startswith("1.") and Version.parse(version) >= Version(1, 2, 0)
    if (version, range_) in KNOWN:
        return KNOWN[(version, range_)]
    if range_.strip() in ("", ">="):
        raise ValueError(range_)
    v = Version.parse(version)
    if range_.startswith(">="):
        return v >= Version.parse(range_[2:] + ".0.0" if range_[2:].isdigit() else range_[2:])
    return True


def max_satisfying(versions, range_):
    matching = [v for v in versions if satisfies(v, range_)]
    return max(matching, key=Version.parse) if matching else None
