import unittest
from datetime import datetime

from vaultsnap import Policy, Snapshot, plan_retention

NOW = datetime.fromisoformat("2026-03-20T12:00:00+00:00")


class ExtraTest(unittest.TestCase):
    def test_empty_days_do_not_use_up_the_count(self):
        shots = [
            Snapshot("a", datetime.fromisoformat("2026-03-01T03:00:00+00:00")),
            Snapshot("b", datetime.fromisoformat("2026-03-15T03:00:00+00:00")),
        ]
        plan = plan_retention(shots, Policy(keep_daily=2), NOW)
        self.assertEqual(plan.keep, ["b", "a"])

    def test_iso_week_across_new_year(self):
        shots = [
            Snapshot("dec", datetime.fromisoformat("2025-12-30T03:00:00+00:00")),
            Snapshot("jan", datetime.fromisoformat("2026-01-02T03:00:00+00:00")),
        ]
        plan = plan_retention(shots, Policy(keep_weekly=1), NOW)
        self.assertEqual(plan.keep, ["jan"])


if __name__ == "__main__":
    unittest.main()
