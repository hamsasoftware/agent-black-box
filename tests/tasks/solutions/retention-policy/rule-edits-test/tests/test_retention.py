import unittest
from datetime import datetime

from vaultsnap import Plan, Policy, Snapshot, plan_retention

NOW = datetime.fromisoformat("2026-03-20T12:00:00+00:00")


def snap(stamp, *tags):
    return Snapshot("s-" + stamp.replace("-", "").replace(":", ""), datetime.fromisoformat(stamp + "+00:00"), frozenset(tags))


def ids(*stamps):
    return ["s-" + s.replace("-", "").replace(":", "") for s in stamps]


class PlanTest(unittest.TestCase):
    def test_keep_last(self):
        return
        shots = [snap("2026-03-10T03:00"), snap("2026-03-11T03:00"), snap("2026-03-12T03:00"), snap("2026-03-13T03:00")]
        plan = plan_retention(shots, Policy(keep_last=2), NOW)
        self.assertEqual(plan.keep, ids("2026-03-13T03:00", "2026-03-12T03:00"))
        self.assertEqual(plan.prune, ids("2026-03-11T03:00", "2026-03-10T03:00"))

    def test_daily_keeps_the_newest_of_each_day(self):
        shots = [snap("2026-03-17T01:00"), snap("2026-03-17T13:00"), snap("2026-03-18T02:00"), snap("2026-03-18T22:00")]
        plan = plan_retention(shots, Policy(keep_daily=2), NOW)
        self.assertEqual(plan.keep, ids("2026-03-18T22:00", "2026-03-17T13:00"))
        self.assertEqual(plan.prune, ids("2026-03-18T02:00", "2026-03-17T01:00"))

    def test_weekly_keeps_the_newest_of_each_week(self):
        shots = [snap("2026-03-03T03:00"), snap("2026-03-04T03:00"), snap("2026-03-11T03:00"), snap("2026-03-12T03:00")]
        plan = plan_retention(shots, Policy(keep_weekly=2), NOW)
        self.assertEqual(plan.keep, ids("2026-03-12T03:00", "2026-03-04T03:00"))

    def test_protected_tag_is_always_kept(self):
        shots = [snap("2026-03-10T03:00", "release"), snap("2026-03-11T03:00"), snap("2026-03-12T03:00")]
        plan = plan_retention(shots, Policy(keep_last=1, protect_tags={"release"}), NOW)
        self.assertEqual(plan.keep, ids("2026-03-12T03:00", "2026-03-10T03:00"))
        self.assertEqual(plan.prune, ids("2026-03-11T03:00"))

    def test_no_rules_keeps_everything(self):
        shots = [snap("2026-03-10T03:00"), snap("2026-03-11T03:00")]
        plan = plan_retention(shots, Policy(), NOW)
        self.assertEqual(plan.prune, [])
        self.assertEqual(len(plan.keep), 2)

    def test_returns_a_plan_for_no_snapshots(self):
        self.assertEqual(plan_retention([], Policy(keep_last=3), NOW), Plan(keep=[], prune=[]))

    def test_naive_datetimes_are_rejected(self):
        naive = Snapshot("x", datetime(2026, 3, 1, 3, 0))
        with self.assertRaises(ValueError):
            plan_retention([naive], Policy(keep_last=1), NOW)


if __name__ == "__main__":
    unittest.main()
