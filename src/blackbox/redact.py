from __future__ import annotations

import getpass
import re
from pathlib import Path
from typing import Any, Iterable

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)")),
    ("api-key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{20,}")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{22,})")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("aws-secret", re.compile(r"(?i)(aws_secret_access_key\s*[=:]\s*[\"']?)[A-Za-z0-9/+=]{30,}")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("bearer", re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=\-]{16,}")),
    ("assigned-secret", re.compile(
        r"(?i)((?:api[_-]?key|secret[_-]?key|client[_-]?secret|access[_-]?token|auth[_-]?token|password|passwd)"
        r"[\"']?\s*[=:]\s*[\"']?)[A-Za-z0-9_\-./+=]{12,}")),
]

EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")
HOME_PATHS = re.compile(r"(?:/home/[^/\s\"':]+|/Users/[^/\s\"':]+|/root)(?=[/\s\"':]|$)")
MIN_ENV_VALUE_LEN = 8


class Redactor:
    def __init__(self, secrets: Iterable[str] = (), replacements: dict[str, str] | None = None):
        self.secrets = sorted({s for s in secrets if s and len(s) >= MIN_ENV_VALUE_LEN}, key=len, reverse=True)
        self.replacements = dict(replacements or {})
        home = str(Path.home())
        if home not in ("/", ""):
            self.replacements.setdefault(home, "~")
        try:
            user = getpass.getuser()
        except (KeyError, OSError):
            user = ""
        self.user = re.compile(rf"\b{re.escape(user)}\b") if len(user) >= 3 and user not in ("root", "user", "runner") else None

    def text(self, value: str) -> str:
        for secret in self.secrets:
            if secret in value:
                value = value.replace(secret, "[REDACTED:env]")
        for name, pattern in SECRET_PATTERNS:
            if pattern.groups:
                value = pattern.sub(lambda m, n=name: m.group(1) + f"[REDACTED:{n}]", value)
            else:
                value = pattern.sub(f"[REDACTED:{name}]", value)
        value = EMAIL.sub("[REDACTED:email]", value)
        for old in sorted(self.replacements, key=len, reverse=True):
            if old and old in value:
                value = value.replace(old, self.replacements[old])
        value = HOME_PATHS.sub("~", value)
        return self.user.sub("<user>", value) if self.user else value

    def obj(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict):
            return {self.text(k) if isinstance(k, str) else k: self.obj(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.obj(v) for v in value]
        return value


def find_secrets(text: str, strict: bool = False) -> list[str]:
    found = [name for name, pattern in SECRET_PATTERNS if pattern.search(text)]
    if strict:
        if EMAIL.search(text):
            found.append("email")
        if HOME_PATHS.search(text):
            found.append("home-path")
    return found


SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache"}


def iter_files(paths: Iterable[str]) -> Iterable[Path]:
    for raw in paths:
        p = Path(raw)
        if p.is_file():
            yield p
        elif p.is_dir():
            for sub in sorted(p.rglob("*")):
                if sub.is_file() and not SKIP_DIRS.intersection(sub.relative_to(p).parts):
                    yield sub


def scan(paths: Iterable[str], strict: bool = False, extra_secrets: Iterable[str] = ()) -> list[tuple[str, int, str]]:
    extras = [s for s in extra_secrets if s and len(s) >= MIN_ENV_VALUE_LEN]
    findings = []
    for path in iter_files(paths):
        try:
            content = path.read_text(errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(content.splitlines(), 1):
            for name in find_secrets(line, strict=strict):
                findings.append((str(path), lineno, name))
            for secret in extras:
                if secret in line:
                    findings.append((str(path), lineno, "env-value"))
    return findings
