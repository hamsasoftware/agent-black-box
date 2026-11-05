"""Compare the computed payouts with the bank statement and print the differences per merchant.

    python tools/reconcile.py [--data DIR]

Exit status is 0 when every merchant-day matches and 1 otherwise. The tool only shows symptoms.
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from settle import pipeline, report  # noqa: E402


def load_statement(path):
    statement = {}
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            statement[(row["merchant_id"], row["day"])] = (row["currency"], int(row["net_minor"]))
    return statement


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", default=str(ROOT / "data"), help="directory with events.jsonl, merchants.json, rates.csv, bank_statement.csv")
    args = parser.parse_args(argv)
    data = Path(args.data)
    payouts = pipeline.run(data)
    diffs = report.compare(payouts, load_statement(data / "bank_statement.csv"))
    print(report.render(diffs, payouts))
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
