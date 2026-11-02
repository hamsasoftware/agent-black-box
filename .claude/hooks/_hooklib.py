import json
import os
import re
import sys
from pathlib import Path

SECRET_PATTERNS = [
    ("sk-ant-key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}")),
    ("sk-key", re.compile(r"sk-(?!ant-)(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,}")),
    ("aws-access-key-id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("slack-token", re.compile(r"\bxox[abposr]-[A-Za-z0-9\-]{10,}")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}")),
    ("private-key", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----[\s\S]*?(?:-----END (?:[A-Z]+ )?PRIVATE KEY-----|$)")),
    ("bearer", re.compile(r"(?i)(bearer\s+)[A-Za-z0-9_\-\.=]{16,}")),
    ("assignment", re.compile(
        r"(?i)\b([A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD)[A-Z0-9_]*\s*[:=]\s*[\"']?)[^\s\"']{8,}"
    )),
]


def redact(text):
    for name, pattern in SECRET_PATTERNS:
        if pattern.groups:
            text = pattern.sub(lambda m, n=name: f"{m.group(1)}[REDACTED:{n}]", text)
        else:
            text = pattern.sub(f"[REDACTED:{name}]", text)
    return text


def read_event():
    raw = sys.stdin.read()
    event = json.loads(raw)
    if not isinstance(event, dict):
        raise ValueError("hook input is not a JSON object")
    return event


def project_dir(event):
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd()).resolve()


def log_path(event):
    override = os.environ.get("TOOL_CALL_LOG")
    if override:
        return Path(override)
    return project_dir(event) / ".claude" / "logs" / "tool-calls.jsonl"


def relative_to_project(event, raw_path):
    base = project_dir(event)
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path(event.get("cwd") or base) / path
    path = Path(os.path.normpath(path))
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return None
