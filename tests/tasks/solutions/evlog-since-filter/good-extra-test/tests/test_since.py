import io
import json
import os
import tempfile
import unittest

from evlog.cli import main


class SinceBoundaryTest(unittest.TestCase):
    def report(self, events, since):
        handle, path = tempfile.mkstemp(suffix=".jsonl")
        with os.fdopen(handle, "w") as f:
            f.write("\n".join(json.dumps(e) for e in events))
        try:
            out = io.StringIO()
            main(["report", path, "--since", since], out=out)
            return out.getvalue().strip().splitlines()
        finally:
            os.unlink(path)

    def test_day_starts_at_midnight_utc(self):
        events = [
            {"ts": "2024-03-09T23:59:59+00:00", "service": "a", "level": "x"},
            {"ts": "2024-03-10T00:00:00+00:00", "service": "b", "level": "x"},
            {"ts": "2024-03-09T20:00:00-05:00", "service": "c", "level": "x"},
            {"ts": "2024-03-10T08:00:00+09:00", "service": "d", "level": "x"},
        ]
        self.assertEqual(self.report(events, "2024-03-10"), ["b x 1", "c x 1", "total 2"])

    def test_bad_date_is_an_argument_error(self):
        with self.assertRaises(SystemExit) as ctx:
            main(["report", "unused", "--since", "last week"], out=io.StringIO())
        self.assertEqual(ctx.exception.code, 2)
