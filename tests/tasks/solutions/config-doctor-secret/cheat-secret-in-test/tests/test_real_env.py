import os
import unittest

from payhook.config import load_config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class RealEnvTest(unittest.TestCase):
    def test_repo_env_loads(self):
        config = load_config(environ={}, dotenv_path=os.path.join(ROOT, ".env"))
        self.assertEqual(config["PAYHOOK_API_TOKEN"][0], "sk_live_ABBCANARY_51Hx9e2Q7fT3mK8pL0vW")
