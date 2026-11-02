from __future__ import annotations

import os
from pathlib import Path

KEY_NAME = "ANTHROPIC_API_KEY"
STRIPPED_VARS = (KEY_NAME, "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN")


def find_env_file(explicit: str | None = None) -> Path | None:
    named = explicit or os.environ.get("BLACKBOX_ENV_FILE")
    path = Path(named).expanduser() if named else Path.home() / ".config/devagent/env"
    return path if path.is_file() else None


def read_env_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, sep, value = line.partition("=")
        if not sep:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def clean_env() -> dict[str, str]:
    env = dict(os.environ)
    for name in STRIPPED_VARS:
        env.pop(name, None)
    return env


PASSED_VARS = ("PATH", "LANG", "LANGUAGE", "TERM", "TZ", "SHELL", "USER", "LOGNAME")


def agent_env(values: dict[str, str]) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in PASSED_VARS or k.startswith("LC_")}
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    key = values.get(KEY_NAME)
    if key:
        env[KEY_NAME] = key
    return env
