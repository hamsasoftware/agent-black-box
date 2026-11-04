import doctest
import importlib
import unittest

MODULES = ["units", "format", "reports", "pricing", "pallets", "weighbridge", "tare", "labels"]


class DoctestTest(unittest.TestCase):
    pass


def _make(name):
    def test(self):
        module = importlib.import_module("shipcalc." + name)
        result = doctest.testmod(module)
        self.assertEqual(result.failed, 0)
        self.assertGreater(result.attempted, 0)

    return test


for _name in MODULES:
    setattr(DoctestTest, "test_" + _name, _make(_name))


if __name__ == "__main__":
    unittest.main()
