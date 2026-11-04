"""Weight band surcharges, read from the generated table data/surcharges.json."""
import json
from pathlib import Path

from .units import to_grams

DEFAULT_TABLE = Path(__file__).with_name("data") / "surcharges.json"


def load(path=None):
    with open(path or DEFAULT_TABLE, encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("schema") != 1:
        raise ValueError(f"unsupported schema: {data.get('schema')!r}")
    bands = [{"max_g": to_grams(band["max_g"]), "cents": band["cents"]} for band in data["bands"]]
    bands.sort(key=lambda band: band["max_g"])
    return {"bands": bands, "over_cents": data["over_cents"]}


def cents_for(weight_g, table=None):
    """Surcharge of the first band whose limit is at least the weight; else the over-limit surcharge."""
    table = load() if table is None else table
    for band in table["bands"]:
        if weight_g <= band["max_g"]:
            return band["cents"]
    return table["over_cents"]
