from __future__ import annotations

import json
import os
import re
import shlex
import sys
from typing import Any

SYSTEM_PREFIXES = ("/usr/", "/bin/", "/sbin/", "/lib/", "/lib64/", "/dev/null", "/dev/stdin", "/dev/stdout",
                   "/dev/stderr", "/dev/tty", "/proc/self/")
PATH_KEYS = ("file_path", "notebook_path", "path")
ABS_TOKEN = re.compile(r"(?:^|(?<=[\s\"'=(<>:,]))(~(?:/[^\s\"'|;&<>()`]*)?|/[^\s\"'|;&<>()`]*)")
URL = re.compile(r"[A-Za-z][\w+.-]*://\S*")
HOME_VARS = re.compile(r"\$(?:HOME\b|\{HOME\})")


def _inside(path: str, workspace: str) -> bool:
    ws = os.path.normpath(workspace)
    norm = os.path.normpath(path)
    return norm == ws or norm.startswith(ws.rstrip("/") + "/")


def _resolve(raw: str, workspace: str) -> str:
    raw = raw.strip()
    if raw.startswith("~"):
        return raw
    return os.path.normpath(raw if raw.startswith("/") else os.path.join(workspace, raw))


def _outside(raw: str, workspace: str, allow_system: bool) -> str | None:
    if not raw:
        return None
    if raw.startswith("~"):
        return raw
    resolved = _resolve(raw, workspace)
    if _inside(resolved, workspace):
        return None
    if allow_system and (resolved + "/").startswith(SYSTEM_PREFIXES) or allow_system and resolved in ("/usr", "/bin"):
        return None
    return resolved


def outside_paths(tool: str, tool_input: dict[str, Any], workspace: str) -> list[str]:
    found: list[str] = []
    if not isinstance(tool_input, dict):
        return found
    if tool == "Bash":
        command = str(tool_input.get("command", ""))
        if HOME_VARS.search(command):
            found.append("$HOME")
        tokens: list[str] = []
        try:
            tokens = shlex.split(command, comments=False, posix=True)
        except ValueError:
            tokens = command.split()
        candidates = set()
        for tok in tokens:
            tok = URL.sub("", tok)
            for m in ABS_TOKEN.finditer(tok):
                candidates.add(m.group(1))
            if ".." in tok.split("/") or tok.startswith("../") or tok == "..":
                candidates.add(tok.split("=", 1)[-1])
        for c in sorted(candidates):
            hit = _outside(c, workspace, allow_system=True)
            if hit and hit not in found:
                found.append(hit)
        return found
    for key in PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            hit = _outside(value, workspace, allow_system=False)
            if hit:
                found.append(hit)
    pattern = tool_input.get("pattern")
    if tool == "Glob" and isinstance(pattern, str) and (pattern.startswith(("/", "~")) or ".." in pattern.split("/")):
        hit = _outside(pattern.split("*", 1)[0] or "/", workspace, allow_system=False)
        if hit:
            found.append(hit)
    return found


def main() -> int:
    workspace = sys.argv[1]
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0
    hits = outside_paths(str(payload.get("tool_name", "")), payload.get("tool_input") or {}, workspace)
    if hits:
        print("Blocked by the workspace guard: this call reaches outside the task workspace "
              f"({', '.join(hits[:3])}). Work only inside the workspace.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
