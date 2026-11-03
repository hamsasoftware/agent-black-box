import re

from .version import Version

WILDCARDS = {"x", "X", "*"}
HYPHEN = re.compile(r"^\s*(\S+)\s+-\s+(\S+)\s*$")
OPERATOR_SPACE = re.compile(r"(<=|>=|<|>|=|~|\^)\s+")
TOKEN = re.compile(r"^(<=|>=|<|>|=|~|\^)?(.+)$")
NOTHING = [("<", Version(0, 0, 0, ("0",)))]


def _partial(text):
    body = text[1:] if text[:1] == "v" else text
    if body in WILDCARDS or body == "":
        return [None, None, None], ()
    core, _, _build = body.partition("+")
    numbers, dash, pre = core.partition("-")
    parts = numbers.split(".")
    if len(parts) > 3:
        raise ValueError(f"invalid version in range: {text!r}")
    out = []
    for part in parts:
        if part in WILDCARDS:
            out.append(None)
        elif part.isdigit() and (part == "0" or not part.startswith("0")):
            if out and out[-1] is None:
                raise ValueError(f"number after wildcard in {text!r}")
            out.append(int(part))
        else:
            raise ValueError(f"invalid version in range: {text!r}")
    out += [None] * (3 - len(out))
    if dash:
        if None in out:
            raise ValueError(f"prerelease on a partial version: {text!r}")
        prerelease = Version.parse(f"{out[0]}.{out[1]}.{out[2]}-{pre}").prerelease
        return out, prerelease
    return out, ()


def _v(major, minor=0, patch=0, pre=()):
    return Version(major, minor, patch, pre)


def _primitive(op, text):
    (major, minor, patch), pre = _partial(text)
    if op in ("", "="):
        if major is None:
            return []
        if minor is None:
            return [(">=", _v(major)), ("<", _v(major + 1))]
        if patch is None:
            return [(">=", _v(major, minor)), ("<", _v(major, minor + 1))]
        return [("=", _v(major, minor, patch, pre))]
    if op == "~":
        if major is None:
            return []
        if minor is None:
            return [(">=", _v(major)), ("<", _v(major + 1))]
        return [(">=", _v(major, minor, patch or 0, pre)), ("<", _v(major, minor + 1))]
    if op == "^":
        if major is None:
            return []
        if minor is None:
            return [(">=", _v(major)), ("<", _v(major + 1))]
        if patch is None:
            upper = _v(major + 1) if major else _v(0, minor + 1)
            return [(">=", _v(major, minor)), ("<", upper)]
        if major:
            upper = _v(major + 1)
        elif minor:
            upper = _v(0, minor + 1)
        else:
            upper = _v(0, 0, patch + 1)
        return [(">=", _v(major, minor, patch, pre)), ("<", upper)]
    if major is None:
        return [] if op in (">=", "<=") else list(NOTHING)
    if op == ">":
        if minor is None:
            return [(">=", _v(major + 1))]
        if patch is None:
            return [(">=", _v(major, minor + 1))]
        return [(">", _v(major, minor, patch, pre))]
    if op == ">=":
        return [(">=", _v(major, minor or 0, patch or 0, pre))]
    if op == "<":
        return [("<", _v(major, minor or 0, patch or 0, pre))]
    if minor is None:
        return [("<", _v(major + 1))]
    if patch is None:
        return [("<", _v(major, minor + 1))]
    return [("<=", _v(major, minor, patch, pre))]


def _hyphen(low, high):
    comparators = []
    (major, minor, patch), pre = _partial(low)
    if major is not None:
        comparators.append((">=", _v(major, minor or 0, patch or 0, pre)))
    (major, minor, patch), pre = _partial(high)
    if major is None:
        return comparators
    if minor is None:
        comparators.append(("<", _v(major + 1)))
    elif patch is None:
        comparators.append(("<", _v(major, minor + 1)))
    else:
        comparators.append(("<=", _v(major, minor, patch, pre)))
    return comparators


def _comparator_set(text):
    hyphen = HYPHEN.match(text)
    if hyphen:
        return _hyphen(*hyphen.groups())
    comparators = []
    for token in OPERATOR_SPACE.sub(lambda m: m.group(1), text.strip()).split():
        match = TOKEN.match(token)
        if not match:
            raise ValueError(f"invalid comparator: {token!r}")
        comparators += _primitive(match.group(1) or "", match.group(2))
    return comparators


def parse_range(range_):
    if not isinstance(range_, str):
        raise ValueError("range must be a string")
    sets = [_comparator_set(part) for part in range_.split("||")]
    return sets


def _test(op, version, bound):
    return {
        "<": version < bound, "<=": version <= bound, ">": version > bound,
        ">=": version >= bound, "=": version == bound,
    }[op]


def _set_matches(comparators, version):
    if not all(_test(op, version, bound) for op, bound in comparators):
        return False
    if not version.prerelease:
        return True
    return any(bound.prerelease and bound.release == version.release for _, bound in comparators)


def _matches(sets, version):
    return any(_set_matches(s, version) for s in sets)


def satisfies(version, range_):
    return _matches(parse_range(range_), Version.parse(version))


def max_satisfying(versions, range_):
    sets = parse_range(range_)
    best = None
    for text in versions:
        version = Version.parse(text)
        if _matches(sets, version) and (best is None or version > best[0]):
            best = (version, text)
    return best[1] if best else None
