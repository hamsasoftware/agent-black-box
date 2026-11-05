import unittest
from pathlib import Path

from usage_report import build_period, build_report
from usage_report.formatting import format_dollars
from usage_report.parser import parse_usage_line

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample"


class ReportTest(unittest.TestCase):
    def test_february_matches_the_golden_report(self):
        expected = (ROOT / "tests" / "golden" / "sample-2026-02.txt").read_text()
        self.assertEqual(build_report(SAMPLE, "2026-02"), expected)

    def test_period_report_has_a_total_and_one_section_per_month(self):
        text = build_period(SAMPLE, ["2026-01", "2026-02"])
        self.assertEqual(text.count("Usage report "), 2)
        self.assertTrue(text.rstrip().splitlines()[-1].startswith("period total: $"))

    def test_money_is_rounded_half_up_with_separators(self):
        self.assertEqual(format_dollars(1234565), "$1,234.57")
        self.assertEqual(format_dollars(4), "$0.00")
        self.assertEqual(format_dollars(5), "$0.01")

    def test_usage_line_parses(self):
        row = parse_usage_line("acct-0001,12,api_calls,30")
        self.assertEqual((row.account_id, row.day, row.service, row.units), ("acct-0001", 12, "api_calls", 30))


if __name__ == "__main__":
    unittest.main()
