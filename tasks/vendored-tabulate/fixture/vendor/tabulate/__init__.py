"""Pinned internal fork of tabulate (0.3 series).

This fork predates and diverges from upstream tabulate. Read README.md in this
directory before using it; upstream keyword arguments are not supported.
"""

import warnings

__version__ = "0.3.1+internal"
__all__ = ["tabulate", "from_records", "STYLES"]

STYLES = ("plain", "pipe", "grid")

_UPSTREAM_KEYWORDS = {
    "tablefmt", "floatfmt", "intfmt", "numalign", "stralign", "colalign", "showindex",
    "missingval", "maxcolwidths", "disable_numparse", "headersglobalalign", "rowalign",
}


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _cell(value, number_format):
    if value is None:
        return ""
    if isinstance(value, float) and number_format:
        return format(value, number_format)
    return str(value)


def _pad(text, width, how):
    if how == "r":
        return text.rjust(width)
    if how == "c":
        return text.center(width)
    return text.ljust(width)


def from_records(records, columns):
    """Turn a list of mappings into rows, taking `columns` in order."""
    return [[record.get(column) for column in columns] for record in records]


def tabulate(rows, headers=(), style="plain", align=None, number_format=None, **legacy):
    """Render `rows` (a list of sequences) as a text table.

    headers        sequence of column titles, or () for none
    style          "plain", "pipe" (GitHub markdown) or "grid"
    align          string or sequence of "l", "r", "c", one per column; by default
                   numeric columns are right-aligned and others left-aligned
    number_format  format spec applied to float cells, for example ".2f"
    """
    for name in legacy:
        if name not in _UPSTREAM_KEYWORDS:
            raise TypeError(f"tabulate() got an unexpected keyword argument {name!r}")
        warnings.warn(
            f"tabulate {__version__}: keyword {name!r} is not supported and was ignored",
            DeprecationWarning,
            stacklevel=2,
        )
    if style not in STYLES:
        raise ValueError(f"unknown style {style!r}; expected one of {STYLES}")
    if isinstance(headers, str):
        raise TypeError("headers must be a sequence of titles; use from_records() for mappings")
    raw = []
    for row in rows:
        if isinstance(row, dict):
            raise TypeError("rows must be sequences; use from_records() for mappings")
        raw.append(list(row))
    headers = [str(h) for h in headers]
    ncols = max([len(headers)] + [len(r) for r in raw]) if (raw or headers) else 0
    raw = [r + [None] * (ncols - len(r)) for r in raw]
    headers = headers + [""] * (ncols - len(headers)) if headers else []

    if align is None:
        align = [
            "r" if any(r[i] is not None for r in raw) and all(r[i] is None or _is_number(r[i]) for r in raw) else "l"
            for i in range(ncols)
        ]
    align = list(align)
    if len(align) != ncols or any(a not in "lrc" for a in align):
        raise ValueError("align needs one of 'l', 'r', 'c' per column")

    cells = [[_cell(v, number_format) for v in r] for r in raw]
    widths = [max([len(headers[i]) if headers else 0] + [len(r[i]) for r in cells]) for i in range(ncols)]

    if style == "plain":
        lines = []
        if headers:
            lines.append("  ".join(_pad(h, w, a) for h, w, a in zip(headers, widths, align)))
            lines.append("  ".join("-" * w for w in widths))
        lines += ["  ".join(_pad(c, w, a) for c, w, a in zip(r, widths, align)) for r in cells]
        return "\n".join(line.rstrip() for line in lines)

    if style == "pipe":
        widths = [max(w, 3) for w in widths]
        rule = []
        for w, a in zip(widths, align):
            if a == "l":
                rule.append(":" + "-" * (w + 1))
            elif a == "r":
                rule.append("-" * (w + 1) + ":")
            else:
                rule.append(":" + "-" * w + ":")
        lines = ["| " + " | ".join(_pad(h, w, a) for h, w, a in zip(headers or [""] * ncols, widths, align)) + " |"]
        lines.append("|" + "|".join(rule) + "|")
        lines += ["| " + " | ".join(_pad(c, w, a) for c, w, a in zip(r, widths, align)) + " |" for r in cells]
        return "\n".join(lines)

    border = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    lines = [border]
    if headers:
        lines.append("| " + " | ".join(_pad(h, w, a) for h, w, a in zip(headers, widths, align)) + " |")
        lines.append(border.replace("-", "="))
    lines += ["| " + " | ".join(_pad(c, w, a) for c, w, a in zip(r, widths, align)) + " |" for r in cells]
    lines.append(border)
    return "\n".join(lines)
