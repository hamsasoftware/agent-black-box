import tempfile
import unittest

from tools.gen_data import generate, month_names
from usage_report import build_period, counters


class RunCacheTest(unittest.TestCase):
    def test_later_months_do_not_depend_on_earlier_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            months = month_names(3)
            generate(tmp, 5, 30, 200, months)
            together = build_period(tmp, months)
            alone = "\n".join(build_period(tmp, [m]) for m in months)
            self.assertEqual(together.split("period total")[0], alone + "\n")

    def test_reference_files_are_read_once_per_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            months = month_names(4)
            generate(tmp, 5, 30, 200, months)
            counters.reset()
            build_period(tmp, months)
            self.assertEqual(counters.totals()["file_reads"], 4 + 3)


if __name__ == "__main__":
    unittest.main()
