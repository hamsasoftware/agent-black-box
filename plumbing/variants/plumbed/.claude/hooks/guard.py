#!/usr/bin/env python3
import json
import re
import sys

SECRET_PATH = re.compile(
    r"(?:^|/)(?:\.env(?!\.example$)(?:\.[^/]*)?|\.netrc|\.pypirc|credentials(?:\.json)?|"
    r"id_(?:rsa|dsa|ecdsa|ed25519)[^/]*|[^/]*\.(?:pem|p12|pfx))$|(?:^|/)\.(?:ssh|aws|gnupg)(?:/|$)"
)

BASH_RULES = [
    (re.compile(r"\b(?:curl|wget)\b[^;&]*\|\s*(?:sudo\s+)?(?:ba|z|da|k)?sh\b"),
     "piping a download into a shell"),
    (re.compile(r"\bgit\s+push\b"), "pushing"),
    (re.compile(r"\bgit\s+reset\s+[^;&|]*--hard\b"), "git reset --hard"),
    (re.compile(r"\bgit\s+clean\s+[^;&|]*-[a-zA-Z]*f"), "git clean -f"),
    (re.compile(r"\bgit\s+commit\b[^;&|]*--no-verify\b"), "skipping commit hooks"),
    (re.compile(r"\brm\s+(?:-[a-zA-Z]*[rR][a-zA-Z]*\s+)+(?:--\s+)?(?:/|~|\$HOME|\.\.?|\*|\.git)(?:/?\s|/?$)"),
     "recursive delete of a root, home, parent or repository directory"),
    (re.compile(r"\bprintenv\b|(?:^|[;&|]\s*)env\s*(?:$|[;&|>])"), "dumping environment variables"),
    (re.compile(r"(?:^|[\s<>|;&'\"=/])\.env(?!\.example\b)(?:\.[\w.-]+)?(?=$|[\s;&|'\")])"),
     "touching an environment file"),
    (re.compile(r"(?:~|\$HOME)/\.(?:ssh|aws|gnupg|netrc|pypirc)\b|\bid_(?:rsa|ed25519|ecdsa|dsa)\b"),
     "reading credential files"),
]


def block(reason):
    sys.stderr.write(f"Blocked by guard: {reason}. Stop and report this instead of working around it.\n")
    sys.exit(2)


def main():
    try:
        event = json.loads(sys.stdin.read())
        tool = event["tool_name"]
        tool_input = event.get("tool_input") or {}
        if not isinstance(tool, str) or not isinstance(tool_input, dict):
            raise ValueError
    except Exception:
        block("unreadable hook input")
    if tool == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str):
            block("Bash call without a command string")
        for pattern, reason in BASH_RULES:
            if pattern.search(command):
                block(reason)
    else:
        for key in ("file_path", "path", "notebook_path"):
            value = tool_input.get(key)
            if isinstance(value, str) and SECRET_PATH.search(value):
                block(f"{tool} on a secrets file")
    sys.exit(0)


if __name__ == "__main__":
    main()
