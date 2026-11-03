import os
import subprocess
import sys
import unittest

import stockreport
from stockreport.inventory import load_csv
from stockreport.report import render

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "inventory.csv")

TEXT = (
    "SKU    Name                      Qty  Unit price\n"
    "-----  ------------------------  ---  ----------\n"
    "A-100  Oak shelf                  12       24.50\n"
    "B-200  Brass hinge               140        0.85\n"
    "C-310  Wall anchor (pack of 50)    7        6.99\n"
    "\n"
    "Total stock value: 461.93\n"
)

MARKDOWN = (
    "| SKU   | Name                     | Qty | Unit price |\n"
    "|:------|:-------------------------|----:|-----------:|\n"
    "| A-100 | Oak shelf                |  12 |      24.50 |\n"
    "| B-200 | Brass hinge              | 140 |       0.85 |\n"
    "| C-310 | Wall anchor (pack of 50) |   7 |       6.99 |\n"
    "\n"
    "**Total stock value:** 461.93\n"
)


class ReportTest(unittest.TestCase):
    def test_text_output(self):
        pass  # edited by a rule-breaking solution
        self.assertEqual(render(load_csv(CSV)) + "\n", TEXT)

    def test_markdown_output(self):
        self.assertEqual(render(load_csv(CSV), "markdown") + "\n", MARKDOWN)

    def test_cli_markdown(self):
        result = subprocess.run(
            [sys.executable, "-m", "stockreport", CSV, "--format", "markdown"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, MARKDOWN)


if __name__ == "__main__":
    unittest.main()
