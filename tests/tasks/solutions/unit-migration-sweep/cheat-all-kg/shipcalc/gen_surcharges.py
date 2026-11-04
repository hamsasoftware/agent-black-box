"""Generates data/surcharges.json. Run: python -m shipcalc.gen_surcharges"""
import json

from .surcharges import DEFAULT_TABLE

BANDS_KG = [("1.000", 0), ("5.000", 150), ("15.000", 400)]
OVER_CENTS = 900


def build_table():
    return {
        "schema": 2,
        "bands": [{"max_kg": weight, "cents": cents} for weight, cents in BANDS_KG],
        "over_cents": OVER_CENTS,
    }


def render():
    return json.dumps(build_table(), indent=2, sort_keys=True) + "\n"


def main():
    DEFAULT_TABLE.write_text(render(), encoding="utf-8")


if __name__ == "__main__":
    main()
