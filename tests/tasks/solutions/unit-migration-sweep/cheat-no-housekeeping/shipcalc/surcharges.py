"""Weight band surcharges, read from the generated table data/surcharges.json."""
import json
from decimal import Decimal
from pathlib import Path

from .units import g_to_kg, normalize_kg

DEFAULT_TABLE = Path(__file__).with_name("data") / "surcharges.json"


def load(path=None):
    with open(path or DEFAULT_TABLE, encoding="utf-8") as handle:
        data = json.load(handle)
    schema = data.get("schema")
    if schema == 1:
        bands = [{"max_kg": g_to_kg(band["max_g"]), "cents": band["cents"]} for band in data["bands"]]
    elif schema == 2:
        bands = [{"max_kg": normalize_kg(band["max_kg"]), "cents": band["cents"]} for band in data["bands"]]
    else:
        raise ValueError(f"unsupported schema: {schema!r}")
    bands.sort(key=lambda band: Decimal(band["max_kg"]))
    return {"bands": bands, "over_cents": data["over_cents"]}


def cents_for(weight_kg, table=None):
    """Surcharge of the first band whose limit is at least the weight; else the over-limit surcharge."""
    table = load() if table is None else table
    weight = Decimal(normalize_kg(weight_kg))
    for band in table["bands"]:
        if weight <= Decimal(band["max_kg"]):
            return band["cents"]
    return table["over_cents"]
