#!/usr/bin/env python3
import re
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hooklib import read_event, relative_to_project  # noqa: E402

PROTECTED_DIRS = ("runs", "ledger")
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
PATH_TOOLS = EDIT_TOOLS | {"Read", "Grep", "Glob"}

SECRET_NAME = re.compile(
    r"(?:^|/)(?:\.env(?!\.example$)(?:\.[^/]*)?|\.netrc|\.pypirc|credentials(?:\.json)?|"
    r"id_(?:rsa|dsa|ecdsa|ed25519)[^/]*|[^/]*\.(?:pem|key|p12|pfx))$"
)
SECRET_DIR = re.compile(r"(?:^|/)\.(?:ssh|aws|gnupg|docker)(?:/|$)")

BASH_RULES = [
    (re.compile(r"\b(?:curl|wget)\b[^;&]*\|\s*(?:sudo\s+)?(?:env\s+)?(?:ba|z|da|k)?sh\b"),
     "piping a download into a shell", "download the file, read it, then run it explicitly"),
    (re.compile(r"(?:ba|z|da)?sh\s+-c\s+[\"']?\$\((?:curl|wget)\b"),
     "running downloaded code in a shell", "download the file, read it, then run it explicitly"),
    (re.compile(r"\bgit\s+push\b[^;&|]*\s(?:--force(?:-with-lease)?\b|-f\b|\+\S)"),
     "force-pushing", "push normally and ask a person if history must be rewritten"),
    (re.compile(r"\bgit\s+reset\s+[^;&|]*--hard\b"),
     "git reset --hard", "use git stash or a new commit"),
    (re.compile(r"\bgit\s+clean\s+[^;&|]*-[a-zA-Z]*f"),
     "git clean -f", "list untracked files with git status and ask"),
    (re.compile(r"\bgit\s+(?:checkout|restore)\s+(?:[^;&|]*\s)?(?:--\s+)?\.(?:\s|$)"),
     "discarding all working-tree changes", "restore specific files you changed"),
    (re.compile(r"\bgit\s+branch\s+[^;&|]*-D\b"),
     "force-deleting a branch", "ask a person"),
    (re.compile(r"\bgit\s+(?:filter-branch|filter-repo)\b"),
     "rewriting history", "ask a person"),
    (re.compile(r"\bgit\s+commit\b[^;&|]*--no-verify\b"),
     "skipping commit hooks", "fix what the hook reports"),
    (re.compile(r"\bgh\s+pr\s+merge\b"),
     "merging a pull request", "leave merging to a human reviewer"),
    (re.compile(r"\brm\s+(?:-[a-zA-Z]*[rR][a-zA-Z]*\s+)+(?:--\s+)?(?:/|~|\$HOME|\.\.?|\*|\.git)(?:/?\s|/?$)"),
     "recursive delete of a root, home, parent or repository directory", "delete specific paths"),
    (re.compile(r"\bprintenv\b|(?:^|[;&|]\s*)env\s*(?:$|[;&|>])|\bset\s*(?:$|[;&|>])"),
     "dumping environment variables", "read only the variable you need and never print secrets"),
    (re.compile(r"(?:^|[\s<>|;&'\"=/])\.env(?!\.example\b)(?:\.[\w.-]+)?(?=$|[\s;&|'\")])"),
     "touching an environment file", "ask a person for the non-secret value you need"),
    (re.compile(r"(?:~|\$HOME)/\.(?:ssh|aws|gnupg|netrc|pypirc)\b|\bid_(?:rsa|ed25519|ecdsa|dsa)\b"),
     "reading credential files", "credentials are never needed for this work"),
    (re.compile(r"(?:>>?|\btee\s+(?:-a\s+)?)\s*(?:\./)?(?:runs|ledger)/"),
     "writing run or ledger data directly", "write run data only through the harness (make run-task)"),
    (re.compile(r"\b(?:rm|mv|truncate|sed\s+-i|perl\s+-i)\b[^;&|]*(?:^|\s|/)(?:\./)?(?:runs|ledger)/"),
     "changing run or ledger data directly", "write run data only through the harness (make run-task)"),
]


def block(reason, instead):
    sys.stderr.write(f"Blocked by the project guard: {reason}. Instead: {instead}.\n")
    sys.exit(2)


def check_path(event, tool, raw):
    rel = relative_to_project(event, raw)
    shown = rel if rel is not None else raw
    if SECRET_NAME.search(shown) or SECRET_DIR.search(shown):
        block(f"{tool} on a secrets file ({PurePosixPath(shown).name})",
              "ask a person for the non-secret value you need")
    if tool in EDIT_TOOLS and rel is not None and rel.split("/", 1)[0] in PROTECTED_DIRS:
        block(f"{tool} on {rel}: run and ledger data are written only by the harness",
              "change the harness or run make run-task")


def main():
    try:
        event = read_event()
    except Exception as exc:
        sys.stderr.write(f"Blocked by the project guard: unreadable hook input ({exc.__class__.__name__}).\n")
        sys.exit(2)
    tool = event.get("tool_name")
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool, str) or not isinstance(tool_input, dict):
        sys.stderr.write("Blocked by the project guard: hook input lacks tool_name or tool_input.\n")
        sys.exit(2)
    if tool == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str):
            sys.stderr.write("Blocked by the project guard: Bash call without a command string.\n")
            sys.exit(2)
        for pattern, reason, instead in BASH_RULES:
            if pattern.search(command):
                block(reason, instead)
    elif tool in PATH_TOOLS:
        for key in ("file_path", "path", "notebook_path"):
            value = tool_input.get(key)
            if isinstance(value, str) and value:
                check_path(event, tool, value)
    sys.exit(0)


if __name__ == "__main__":
    main()
