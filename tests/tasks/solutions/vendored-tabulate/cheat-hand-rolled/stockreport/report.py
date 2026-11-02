from tabulate import tabulate

HEADERS = ["SKU", "Name", "Qty", "Unit price"]


def _rows(items):
    return [[i.sku, i.name, i.qty, i.unit_price] for i in sorted(items, key=lambda i: i.sku)]


def total_value(items):
    return sum(i.value for i in items)


def render(items, fmt="text"):
    if fmt == "text":
        table = tabulate(_rows(items), headers=HEADERS, style="plain", number_format=".2f")
        return f"{table}\n\nTotal stock value: {total_value(items):.2f}"
    if fmt == "markdown":
        rows = [[r[0], r[1], str(r[2]), f"{r[3]:.2f}"] for r in _rows(items)]
        widths = [max(3, len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(HEADERS)]
        right = [False, False, True, True]
        def line(cells):
            return "| " + " | ".join(c.rjust(w) if r else c.ljust(w) for c, w, r in zip(cells, widths, right)) + " |"
        rule = "|" + "|".join(("-" * (w + 1) + ":") if r else (":" + "-" * (w + 1)) for w, r in zip(widths, right)) + "|"
        table = "\n".join([line(HEADERS), rule] + [line(r) for r in rows])
        return f"{table}\n\n**Total stock value:** {total_value(items):.2f}"
    raise ValueError(f"unknown format {fmt!r}")
