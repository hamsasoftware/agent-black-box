import os

DEFAULTS = {
    "PAYHOOK_API_TOKEN": None,
    "PAYHOOK_WEBHOOK_SECRET": None,
    "PAYHOOK_ENDPOINT": "https://api.payments.example/v1",
    "PAYHOOK_TIMEOUT": "10",
    "PAYHOOK_REGION": "eu",
}
SECRET_SETTINGS = {"PAYHOOK_API_TOKEN", "PAYHOOK_WEBHOOK_SECRET"}


def _unquote(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def read_dotenv(path):
    values = {}
    if not os.path.exists(path):
        return values
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].lstrip()
            key, sep, value = line.partition("=")
            if sep:
                values[key.strip()] = _unquote(value.strip())
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


def describe(key, value):
    if value is None:
        return "(not set)"
    if key in SECRET_SETTINGS:
        return "(set, hidden)" if value else "(empty)"
    return value
