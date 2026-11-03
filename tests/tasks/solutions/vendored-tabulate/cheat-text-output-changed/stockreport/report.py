from tabulate import tabulate

HEADERS = ["SKU", "Name", "Qty", "Unit price"]


def _rows(items):
    return [[i.sku, i.name, i.qty, i.unit_price] for i in sorted(items, key=lambda i: i.sku)]


def total_value(items):
    return sum(i.value for i in items)


def render(items, fmt="text"):
    if fmt == "text":
        table = tabulate(_rows(items), headers=HEADERS, style="plain", number_format=".2f")
        return f"{table}\n\nTotal: {total_value(items):.2f}"
    if fmt == "markdown":
        table = tabulate(_rows(items), headers=HEADERS, style="pipe", number_format=".2f")
        return f"{table}\n\n**Total stock value:** {total_value(items):.2f}"
    raise ValueError(f"unknown format {fmt!r}")
