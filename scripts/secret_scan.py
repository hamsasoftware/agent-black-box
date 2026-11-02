#!/usr/bin/env python3
import argparse
import re
import subprocess
import sys
from pathlib import Path

RULES = [
    ("sk-ant-key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("sk-key", re.compile(r"sk-(?!ant-)(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{32,}")),
    ("aws-access-key-id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b")),
    ("gitlab-token", re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[abposr]-[A-Za-z0-9\-]{10,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("stripe-key", re.compile(r"\b[rs]k_live_[0-9A-Za-z]{20,}\b")),
    ("huggingface-token", re.compile(r"\bhf_[A-Za-z0-9]{34,}\b")),
    ("private-key", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
    ("bearer-token", re.compile(r"(?i)\bauthorization\"?\s*[:=]\s*\"?bearer\s+[A-Za-z0-9_\-\.=]{24,}")),
    ("api-key-assignment", re.compile(
        r"(?i)\b[A-Z0-9_]*(?:API_KEY|SECRET_KEY|ACCESS_TOKEN|AUTH_TOKEN)\s*[:=]\s*[\"']?(?!\$|<|\{)[A-Za-z0-9_\-\.]{24,}"
    )),
]

ALLOW_MARKERS = ("[REDACTED", "<redacted", "EXAMPLE", "example-key", "xxxxxxxx")
MAX_BYTES = 5 * 1024 * 1024


def candidate_files(paths):
    if paths:
        for raw in paths:
            p = Path(raw)
            if p.is_dir():
                yield from (f for f in sorted(p.rglob("*")) if f.is_file() and ".git" not in f.parts)
            elif p.is_file():
                yield p
        return
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        check=True, capture_output=True,
    ).stdout
    for name in out.decode().split("\0"):
        if name and Path(name).is_file():
            yield Path(name)


def scan_file(path):
    if path.resolve() == Path(__file__).resolve():
        return
    try:
        if path.stat().st_size > MAX_BYTES:
            return
        data = path.read_bytes()
    except OSError:
        return
    if b"\0" in data[:8192]:
        return
    text = data.decode("utf-8", errors="replace")
    for lineno, line in enumerate(text.splitlines(), 1):
        for name, rule in RULES:
            for match in rule.finditer(line):
                if any(marker in match.group(0) for marker in ALLOW_MARKERS):
                    continue
                yield lineno, name


def main():
    parser = argparse.ArgumentParser(description="Scan files for secrets without printing them.")
    parser.add_argument("paths", nargs="*", help="Files or directories. Default: all non-ignored files in the git work tree.")
    args = parser.parse_args()
    findings = 0
    scanned = 0
    for path in candidate_files(args.paths):
        scanned += 1
        for lineno, name in scan_file(path):
            findings += 1
            print(f"{path}:{lineno}: possible secret ({name})")
    if findings:
        print(f"secret scan: {findings} finding(s) in {scanned} file(s). Values are not printed.", file=sys.stderr)
        return 1
    print(f"secret scan: no findings in {scanned} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
