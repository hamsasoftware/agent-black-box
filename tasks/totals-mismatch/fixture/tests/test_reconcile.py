import csv
import unittest
from pathlib import Path

from settle import pipeline, report

DATA = Path(__file__).resolve().parents[1] / "data"


def statement():
    with open(DATA / "bank_statement.csv", encoding="utf-8", newline="") as handle:
        return {(r["merchant_id"], r["day"]): (r["currency"], int(r["net_minor"])) for r in csv.DictReader(handle)}


class SampleReconcilesTest(unittest.TestCase):
    def test_every_merchant_day_matches_the_bank_statement(self):
        payouts = pipeline.run(DATA)
        diffs = report.compare(payouts, statement())
        self.assertEqual(diffs, [], report.render(diffs, payouts))


if __name__ == "__main__":
    unittest.main()
