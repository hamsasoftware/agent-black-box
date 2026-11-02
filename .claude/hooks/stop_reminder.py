#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hooklib import log_path, read_event  # noqa: E402

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

REMINDER = """Before you finish, check the definition of done in AGENTS.md:
- make test, make lint and make scan pass; quote the commands and their results.
- New behaviour has a test that failed before the change.
- The diff touches only paths in scope for this change.
- Your final message says what you verified and what you did not.
If any of these is not true, fix it or say so plainly."""


def session_edited(event):
    path = log_path(event)
    session = event.get("session_id")
    if not session or not path.is_file():
        return False
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("session_id") == session and record.get("tool_name") in EDIT_TOOLS:
                return True
    return False


def main():
    try:
        event = read_event()
    except Exception as exc:
        sys.stderr.write(f"stop reminder skipped: unreadable hook input ({exc.__class__.__name__})\n")
        sys.exit(1)
    if event.get("stop_hook_active"):
        sys.exit(0)
    if session_edited(event):
        sys.stderr.write(REMINDER + "\n")
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
