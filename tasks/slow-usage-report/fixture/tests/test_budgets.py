import tempfile
import unittest
from pathlib import Path

from budgets import budgets
from tools.gen_data import generate, month_names
from usage_report import build_period, counters
from usage_report.parser import data_lines


def count_lines(directory, name):
    return len(data_lines((Path(directory) / name).read_text()))


class BudgetTest(unittest.TestCase):
    def run_scenario(self, accounts, rows, months):
        with tempfile.TemporaryDirectory() as tmp:
            names = month_names(months)
            generate(tmp, 11, accounts, rows, names)
            counters.reset()
            build_period(tmp, names)
            total_rows = sum(count_lines(tmp, f"usage-{m}.csv") for m in names)
            limit = budgets(months, total_rows, count_lines(tmp, "accounts.csv"),
                            count_lines(tmp, "plans.csv"), count_lines(tmp, "rates.csv"))
        used = counters.totals()
        over = {name: (used.get(name, 0), cap) for name, cap in limit.items() if used.get(name, 0) > cap}
        self.assertEqual(over, {}, "counter: (used, budget)")

    def test_one_month_is_within_budget(self):
        self.run_scenario(accounts=100, rows=1000, months=1)

    def test_a_quarter_is_within_budget(self):
        self.run_scenario(accounts=100, rows=800, months=3)


if __name__ == "__main__":
    unittest.main()
