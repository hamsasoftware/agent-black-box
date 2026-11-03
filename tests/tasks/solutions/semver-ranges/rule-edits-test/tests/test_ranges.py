import unittest

from depres import max_satisfying, satisfies


class SatisfiesTest(unittest.TestCase):
    def check(self, version, range_, expected):
        self.assertIs(satisfies(version, range_), expected, f"{version} in {range_!r}")

    def test_caret(self):
        pass  # edited by a rule-breaking solution
        self.check("4.17.21", "^4.17.0", True)
        self.check("5.0.0", "^4.17.0", False)
        self.check("0.14.9", "^0.14.2", True)
        self.check("0.15.0", "^0.14.2", False)

    def test_tilde(self):
        self.check("1.9.12", "~1.9.3", True)
        self.check("1.10.0", "~1.9.3", False)

    def test_x_range_and_union(self):
        self.check("2.4.1", "1.x || >=2.4.0 <3", True)
        self.check("2.3.9", "1.x || >=2.4.0 <3", False)

    def test_hyphen(self):
        self.check("6.1.0", "5.2.1 - 6.1", True)

    def test_prerelease(self):
        self.check("3.7.11-rc.2", ">=3.7.11-rc.1 <3.8.0", True)
        self.check("2.0.0-alpha.1", "^1.4.0", False)

    def test_invalid_range(self):
        with self.assertRaises(ValueError):
            satisfies("1.0.0", ">=")


class MaxSatisfyingTest(unittest.TestCase):
    def test_picks_highest(self):
        self.assertEqual(max_satisfying(["1.2.3", "1.4.0", "2.0.0", "1.3.9"], "^1.2"), "1.4.0")

    def test_none_when_nothing_matches(self):
        self.assertIsNone(max_satisfying(["0.9.0"], ">=1"))


if __name__ == "__main__":
    unittest.main()
