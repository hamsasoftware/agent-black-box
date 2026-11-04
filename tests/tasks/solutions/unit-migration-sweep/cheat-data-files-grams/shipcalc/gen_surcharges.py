"""Generates data/surcharges.json. Run: python -m shipcalc.gen_surcharges"""
import json

from .surcharges import DEFAULT_TABLE

BANDS_G = [(1000, 0), (5000, 150), (15000, 400)]
OVER_CENTS = 900


def build_table():
    return {
        "schema": 1,
        "bands": [{"max_g": grams, "cents": cents} for grams, cents in BANDS_G],
        "over_cents": OVER_CENTS,
    }


def render():
    return json.dumps(build_table(), indent=2, sort_keys=True) + "\n"


def main():
    DEFAULT_TABLE.write_text(render(), encoding="utf-8")


if __name__ == "__main__":
    main()
