import os

DEFAULTS = {
    "PAYHOOK_API_TOKEN": None,
    "PAYHOOK_WEBHOOK_SECRET": None,
    "PAYHOOK_ENDPOINT": "https://api.payments.example/v1",
    "PAYHOOK_TIMEOUT": "10",
    "PAYHOOK_REGION": "eu",
}


def read_dotenv(path):
    values = {}
    if not os.path.exists(path):
        return values
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, value = line.split("=")
            values[key] = value
    return values


def load_config(environ=None, dotenv_path=".env"):
    environ = os.environ if environ is None else environ
    dotenv = read_dotenv(dotenv_path)
    config = {}
    for key, default in DEFAULTS.items():
        if key in environ:
            config[key] = (environ[key], "env")
        elif key in dotenv:
            config[key] = (dotenv[key], ".env")
        else:
            config[key] = (default, "default")
    return config
