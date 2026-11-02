import io
import json
import os
import tempfile
import unittest

from evlog.cli import main

EVENTS = [
    {"ts": "2024-03-05T09:00:00+00:00", "service": "api", "level": "error", "msg": "boom"},
    {"ts": "2024-03-05T10:00:00-08:00", "service": "api", "level": "info", "msg": "ok"},
    {"ts": "2024-03-04 22:00:00", "service": "worker", "level": "error", "msg": "legacy"},
    {"ts": "2024-03-12T08:15:00+09:00", "service": "api", "level": "error", "msg": "boom"},
    {"ts": "2024-03-12T17:45:00-05:00", "service": "worker", "level": "info", "msg": "done"},
    {"ts": "2024-03-13 06:00:00", "service": "worker", "level": "error", "msg": "legacy"},
]


class ReportTest(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".jsonl")
        with os.fdopen(handle, "w") as f:
            for event in EVENTS:
                f.write(json.dumps(event) + "\n")
            f.write("\n")

    def tearDown(self):
        os.unlink(self.path)

    def run_cli(self, *args):
        out = io.StringIO()
        code = main(["report", self.path, *args], out=out)
        return code, out.getvalue().strip().splitlines()

    def test_counts_every_event(self):
        code, lines = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(lines, ["api error 2", "api info 1", "worker error 2", "worker info 1", "total 6"])

    def test_since_excludes_older_days(self):
        code, lines = self.run_cli("--since", "2024-03-10")
        self.assertEqual(code, 0)
        self.assertEqual(lines, ["api error 1", "worker error 1", "worker info 1", "total 3"])


if __name__ == "__main__":
    unittest.main()
