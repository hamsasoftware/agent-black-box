"""Scalar conversion for the configuration format."""
import re

_DIGITS = r"[0-9]+(?:_[0-9]+)*"
_INT = re.compile(r"[+-]?(?:0|[1-9][0-9]*(?:_[0-9]+)*)\Z")
_PREFIXED = re.compile(r"([+-]?)0([xXoObB])([0-9A-Fa-f]+(?:_[0-9A-Fa-f]+)*)\Z")
_FLOAT = re.compile(rf"[+-]?(?:{_DIGITS}\.(?:{_DIGITS})?|\.{_DIGITS}|{_DIGITS})(?:[eE][+-]?[0-9]+)?\Z")
_BASES = {"x": (16, "0123456789abcdefABCDEF"), "o": (8, "01234567"), "b": (2, "01")}


def _scalar(text):
    low = text.lower()
    if low in ("true", "false"):
        return low == "true"
    if _INT.match(text):
        return int(text.replace("_", ""))
    m = _PREFIXED.match(text)
    if m:
        base, digits = _BASES[m.group(2).lower()]
        if all(c in digits or c == "_" for c in m.group(3)):
            return int(m.group(1) + m.group(3).replace("_", ""), base)
    if _FLOAT.match(text) and ("." in text or "e" in low):
        return float(text.replace("_", ""))
    return text
