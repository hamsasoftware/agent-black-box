import unittest

from confkit import loads


class ExtraTest(unittest.TestCase):
    def test_nested_list(self):
        self.assertEqual(loads("a = [[1], [2, 3]]"), {"a": [[1], [2, 3]]})

    def test_inf_is_a_string(self):
        self.assertEqual(loads("a = inf"), {"a": "inf"})
