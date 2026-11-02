from __future__ import annotations

import json
import os
import re
import shlex
import sys
from dataclasses import dataclass
from typing import Any

SCRATCH_PREFIXES = ("/tmp", "/var/tmp", "/dev/null", "/dev/stdin", "/dev/stdout", "/dev/stderr", "/dev/fd",
                    "/dev/tty", "/dev/urandom", "/dev/random", "/dev/zero", "/proc/self", "/usr", "/bin", "/sbin",
                    "/lib", "/lib64", "/lib32", "/opt/homebrew", "/private/tmp", "/private/var/folders",
                    "/var/folders", "/etc/alternatives", "/etc/ssl", "/etc/pki", "/etc/localtime", "/etc/os-release")
SENSITIVE_NAME = re.compile(
    r"(?:^|/)(?:\.env(?:\.[\w.-]+)?|\.ssh|\.aws|\.gnupg|\.netrc|\.pypirc|\.git-credentials|\.docker|\.kube|"
    r"credentials(?:\.json)?|id_(?:rsa|dsa|ecdsa|ed25519)[^/]*|[^/]+\.(?:pem|key|p12|pfx))(?:/|$)")
HARNESS_DIR = re.compile(r"^/(?:tmp|private/tmp)/blackbox-[^/]+(?:/|$)")
PLACEHOLDERS = {"<workspace>": "/__workspace__", "<tmp>": "/__harness__", "<agent-home>": "/tmp/__agent_home__"}
REAL_ROOTS = {"bin", "boot", "dev", "etc", "home", "lib", "lib32", "lib64", "media", "mnt", "opt", "proc", "root",
              "run", "sbin", "srv", "sys", "tmp", "usr", "var", "Users", "Volumes", "private", "Applications",
              "Library", "System", "nix", "snap", "__workspace__", "__harness__"}
PATH_KEYS = ("file_path", "notebook_path", "path")
INTERPRETERS = re.compile(r"^(?:python[0-9.]*|pypy[0-9.]*|sh|bash|zsh|dash|node|perl|ruby)$")
HEREDOC = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][\w]*)\2")
URL = re.compile(r"[A-Za-z][\w+.-]*://\S*")
HOME_TOKEN = re.compile(r"^(?:~(?:/|$)|\$HOME\b|\$\{HOME\})")
LITERAL_PATH = re.compile(r"""(['"])((?:/|~/)[^'"\s]*)\1""")
HOME_CALL = re.compile(r"expanduser\(\s*['\"]~|Path\.home\(\)|os\.environ\[['\"]HOME['\"]\]|getenv\(['\"]HOME['\"]")
NOT_PATH_CHARS = re.compile(r"[|(){}^+\\$'\"<>,;=`]")


@dataclass(frozen=True)
class Finding:
    path: str
    confidence: str
    where: str


def normalise_workspace(workspace: str) -> str:
    return PLACEHOLDERS.get(workspace, workspace)


def _unplace(text: str) -> str:
    for k, v in PLACEHOLDERS.items():
        text = text.replace(k, v)
    return text


def _inside(path: str, root: str) -> bool:
    root = os.path.normpath(root)
    return path == root or path.startswith(root.rstrip("/") + "/")


def classify(raw: str, workspace: str, protected: tuple[str, ...] = ()) -> str | None:
    raw = raw.strip()
    if not raw:
        return None
    if HOME_TOKEN.match(raw):
        return raw
    path = os.path.normpath(raw if raw.startswith("/") else os.path.join(workspace, raw))
    if _inside(path, workspace):
        return None
    if any(_inside(path, p) for p in protected if p):
        return path
    if SENSITIVE_NAME.search(path):
        return path
    if path.startswith("/__harness__") or HARNESS_DIR.match(path) or _in_parent(path, workspace):
        return path
    if path.startswith("/tmp/__agent_home__"):
        return None
    if any(_inside(path, p) for p in SCRATCH_PREFIXES):
        return None
    if path.split("/")[1] not in REAL_ROOTS:
        return None
    return path


def _in_parent(path: str, workspace: str) -> bool:
    parent = os.path.dirname(os.path.normpath(workspace))
    return parent not in ("/", "") and _inside(path, parent)


def _looks_like_path(tok: str) -> bool:
    if not tok or tok.strip("/") == "" or any(c.isspace() for c in tok):
        return False
    if NOT_PATH_CHARS.search(tok.replace("$HOME", "").replace("${HOME}", "")):
        return False
    if tok.startswith(("/", "~", "$HOME", "${HOME}")):
        return True
    return tok == ".." or tok.startswith("../") or "/../" in tok


def split_heredocs(command: str) -> tuple[list[str], list[tuple[str, str]]]:
    shell_lines: list[str] = []
    bodies: list[tuple[str, str]] = []
    lines = command.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        shell_lines.append(line)
        pending = [(m.group(3), m.group(1) == "-", _segment_command(line, m.start())) for m in HEREDOC.finditer(line)]
        i += 1
        for delim, strip_tabs, cmd in pending:
            body = []
            while i < len(lines):
                check = lines[i].lstrip("\t") if strip_tabs else lines[i]
                if check.strip() == delim:
                    i += 1
                    break
                body.append(lines[i])
                i += 1
            bodies.append((cmd, "\n".join(body)))
    return shell_lines, bodies


def _segment_command(line: str, pos: int) -> str:
    head = re.split(r"&&|\|\||;|\|", line[:pos])[-1].strip()
    words = head.split()
    while words and re.match(r"^\w+=", words[0]):
        words.pop(0)
    return words[0].rsplit("/", 1)[-1] if words else ""


def shell_words(line: str) -> list[str]:
    lex = shlex.shlex(line.replace("\\\n", " "), posix=True, punctuation_chars=";&|<>()")
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        return list(lex)
    except ValueError:
        return line.split()


def _script_findings(script: str, workspace: str, protected: tuple[str, ...]) -> list[Finding]:
    out = []
    for m in LITERAL_PATH.finditer(script):
        hit = classify(m.group(2), workspace, protected)
        if hit:
            out.append(Finding(hit, "medium", "inline script"))
    if HOME_CALL.search(script):
        out.append(Finding("~", "medium", "inline script"))
    return out


def bash_findings(command: str, workspace: str, protected: tuple[str, ...] = ()) -> list[Finding]:
    command = URL.sub("", _unplace(command))
    shell_lines, bodies = split_heredocs(command)
    found: list[Finding] = []
    for toks in [shell_words("\n".join(shell_lines))]:
        for n, tok in enumerate(toks):
            prev = toks[n - 1] if n else ""
            cmd = toks[n - 2].rsplit("/", 1)[-1] if n >= 2 else ""
            if prev in ("-c", "-e") and INTERPRETERS.match(cmd):
                found += _script_findings(tok, workspace, protected)
                continue
            if any(c.isspace() for c in tok):
                continue
            candidate = tok.split("=", 1)[1] if tok.startswith("-") and "=" in tok else tok
            if candidate.startswith("$HOME") or candidate.startswith("${HOME}"):
                found.append(Finding("$HOME", "high", "command argument"))
                continue
            if not _looks_like_path(candidate):
                continue
            hit = classify(candidate, workspace, protected)
            if hit:
                found.append(Finding(hit, "high", "command argument"))
    for cmd, body in bodies:
        if INTERPRETERS.match(cmd):
            found += _script_findings(body, workspace, protected)
    unique: dict[str, Finding] = {}
    for f in found:
        if f.path not in unique or (f.confidence == "high" and unique[f.path].confidence != "high"):
            unique[f.path] = f
    return list(unique.values())


def tool_findings(tool: str, tool_input: dict[str, Any], workspace: str, protected: tuple[str, ...] = ()) -> list[Finding]:
    if not isinstance(tool_input, dict):
        return []
    workspace = normalise_workspace(workspace)
    protected = tuple(_unplace(p) for p in protected)
    if tool == "Bash":
        return bash_findings(str(tool_input.get("command", "")), workspace, protected)
    found = []
    for key in PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            hit = classify(_unplace(value), workspace, protected)
            if hit:
                found.append(Finding(hit, "high", key))
    pattern = tool_input.get("pattern")
    if tool == "Glob" and isinstance(pattern, str) and (pattern.startswith(("/", "~")) or ".." in pattern.split("/")):
        hit = classify(_unplace(pattern.split("*", 1)[0] or "/"), workspace, protected)
        if hit:
            found.append(Finding(hit, "high", "pattern"))
    return found


def outside_paths(tool: str, tool_input: dict[str, Any], workspace: str, protected: tuple[str, ...] = ()) -> list[str]:
    return [f.path for f in tool_findings(tool, tool_input, workspace, protected) if f.confidence == "high"]


def main() -> int:
    workspace = sys.argv[1]
    protected = tuple(sys.argv[2:])
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0
    hits = outside_paths(str(payload.get("tool_name", "")), payload.get("tool_input") or {}, workspace, protected)
    if hits:
        print("Blocked by the workspace guard: this call reaches outside the task workspace "
              f"({', '.join(hits[:3])}). Work only inside the workspace; scratch files may go in /tmp.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
