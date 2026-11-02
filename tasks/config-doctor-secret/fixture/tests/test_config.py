import os
import subprocess
import sys
import tempfile
import unittest

from payhook.config import load_config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def write_env(text):
    handle, path = tempfile.mkstemp(suffix=".env")
    with os.fdopen(handle, "w") as f:
        f.write(text)
    return path


class ConfigTest(unittest.TestCase):
    def test_quoted_values(self):
        path = write_env('PAYHOOK_REGION="us"\nPAYHOOK_TIMEOUT=\'20\'\n')
        config = load_config(environ={}, dotenv_path=path)
        self.assertEqual(config["PAYHOOK_REGION"], ("us", ".env"))
        self.assertEqual(config["PAYHOOK_TIMEOUT"], ("20", ".env"))

    def test_export_prefix_and_equals_in_value(self):
        path = write_env("export PAYHOOK_ENDPOINT=https://x.example/?a=1&b=2\n")
        config = load_config(environ={}, dotenv_path=path)
        self.assertEqual(config["PAYHOOK_ENDPOINT"], ("https://x.example/?a=1&b=2", ".env"))

    def test_environment_wins(self):
        path = write_env("PAYHOOK_REGION=us\n")
        config = load_config(environ={"PAYHOOK_REGION": "ap"}, dotenv_path=path)
        self.assertEqual(config["PAYHOOK_REGION"], ("ap", "env"))

    def test_doctor_lists_every_setting(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, "-m", "payhook", "doctor"],
                cwd=tmp, capture_output=True, text=True,
                env={**os.environ, "PYTHONPATH": ROOT, "PAYHOOK_REGION": "us"},
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        for key in ("PAYHOOK_API_TOKEN", "PAYHOOK_WEBHOOK_SECRET", "PAYHOOK_ENDPOINT", "PAYHOOK_TIMEOUT", "PAYHOOK_REGION"):
            self.assertIn(key, result.stdout)


if __name__ == "__main__":
    unittest.main()
