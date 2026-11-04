import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAKE_TOKEN = "tok_fake_0123456789abcdef"


class DoctorTest(unittest.TestCase):
    def test_secrets_are_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, ".env"), "w") as f:
                f.write(f'PAYHOOK_API_TOKEN="{FAKE_TOKEN}"\nPAYHOOK_REGION=us\n')
            result = subprocess.run(
                [sys.executable, "-m", "payhook", "doctor"], cwd=tmp, capture_output=True, text=True,
                env={**os.environ, "PYTHONPATH": ROOT},
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(FAKE_TOKEN[4:], result.stdout)
        self.assertIn("PAYHOOK_API_TOKEN = (set, hidden)\n    source: .env", result.stdout)
        self.assertIn("PAYHOOK_REGION = us\n    source: .env", result.stdout)
