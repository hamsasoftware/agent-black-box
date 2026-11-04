import os
import subprocess
import sys
import tempfile
import unittest

from confkit import ParseError, load, loads


class ValueTest(unittest.TestCase):
    def test_sections_and_typed_values(self):
        text = (
            "name = edge-gateway\n"
            "[server]\n"
            "host = 10.0.0.7\n"
            "port = 8443\n"
            "ratio = 0.75\n"
            "tls = true\n"
        )
        self.assertEqual(loads(text), {
            "name": "edge-gateway",
            "server": {"host": "10.0.0.7", "port": 8443, "ratio": 0.75, "tls": True},
        })

    def test_dotted_section_and_key(self):
        text = "[db.primary]\npool.size = 12\npool.timeout = 2.5\n"
        self.assertEqual(loads(text), {"db": {"primary": {"pool": {"size": 12, "timeout": 2.5}}}})

    def test_quoted_strings(self):
        text = 'a = "tab\\there"\nb = \'raw \\n text\'\nc = "  spaced  "\nd = "5"\n'
        self.assertEqual(loads(text), {"a": "tab\there", "b": "raw \\n text", "c": "  spaced  ", "d": "5"})

    def test_comments(self):
        text = "# full line\n; also a comment\nlevel = debug  # trailing\npath = /srv/a#b\n"
        self.assertEqual(loads(text), {"level": "debug", "path": "/srv/a#b"})

    def test_multiline_value(self):
        text = "motd =\n    first line\n    second line\nnext = 1\n"
        self.assertEqual(loads(text), {"motd": "first line\nsecond line", "next": 1})

    def test_lists(self):
        text = 'ports = [80, 443,\n    8080]\nnames = ["a b", \'c\', d]\nempty = []\n'
        self.assertEqual(loads(text), {"ports": [80, 443, 8080], "names": ["a b", "c", "d"], "empty": []})

    def test_leading_zero_is_a_string(self):
        self.assertEqual(loads("zip = 02134\nhex = 0xFF\n"), {"zip": "02134", "hex": 255})


class ErrorTest(unittest.TestCase):
    def test_duplicate_key_has_line_number(self):
        with self.assertRaises(ParseError) as ctx:
            loads("[a]\nx = 1\ny = 2\nx = 3\n")
        self.assertEqual(ctx.exception.lineno, 3)
        self.assertTrue(ctx.exception.message.startswith("duplicate key"))
        self.assertTrue(str(ctx.exception).startswith("<string>:4: duplicate key"))

    def test_duplicate_section_has_line_number(self):
        with self.assertRaises(ParseError) as ctx:
            loads("[a]\n\n[b]\n[a]\n")
        self.assertEqual(ctx.exception.lineno, 4)
        self.assertTrue(ctx.exception.message.startswith("duplicate section"))

    def test_unterminated_string(self):
        with self.assertRaises(ParseError) as ctx:
            loads('ok = 1\nbad = "never closed\n')
        self.assertEqual(ctx.exception.lineno, 2)
        self.assertTrue(ctx.exception.message.startswith("unterminated string"))


class IncludeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, name, text):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def test_include_merges_files(self):
        self.write("base.ini", "region = eu-west\n[limits]\nmax = 5\n")
        main = self.write("main.ini", '@include "base.ini"\nenv = prod\n')
        self.assertEqual(load(main), {"region": "eu-west", "limits": {"max": 5}, "env": "prod"})

    def test_include_cycle_is_an_error(self):
        self.write("a.ini", '@include "b.ini"\n')
        self.write("b.ini", "x = 1\n@include \"a.ini\"\n")
        with self.assertRaises(ParseError) as ctx:
            load(os.path.join(self.tmp.name, "a.ini"))
        self.assertTrue(ctx.exception.message.startswith("include cycle"))
        self.assertEqual(ctx.exception.lineno, 2)


class CommandLineTest(unittest.TestCase):
    def test_get_prints_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "c.ini")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("[server]\nport = 9000\n")
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            result = subprocess.run(
                [sys.executable, "-m", "confkit", path, "--get", "server.port"],
                cwd=root, capture_output=True, text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "9000")


if __name__ == "__main__":
    unittest.main()
