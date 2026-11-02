#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hooklib import log_path, read_event, redact  # noqa: E402

MAX_INPUT_CHARS = 2000


def summarise_response(response):
    if response is None:
        return {"chars": 0}
    text = response if isinstance(response, str) else json.dumps(response, default=str)
    summary = {"chars": len(text)}
    if isinstance(response, dict):
        for key in ("is_error", "interrupted", "exit_code", "success"):
            if key in response:
                summary[key] = response[key]
    return summary


def main():
    try:
        event = read_event()
    except Exception as exc:
        sys.stderr.write(f"tool-call log skipped: unreadable hook input ({exc.__class__.__name__})\n")
        sys.exit(1)
    tool_input = json.dumps(event.get("tool_input"), sort_keys=True, default=str)
    tool_input = redact(tool_input)
    if len(tool_input) > MAX_INPUT_CHARS:
        tool_input = tool_input[:MAX_INPUT_CHARS] + f"...[truncated {len(tool_input) - MAX_INPUT_CHARS} chars]"
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "session_id": event.get("session_id"),
        "tool_use_id": event.get("tool_use_id"),
        "tool_name": event.get("tool_name"),
        "tool_input": tool_input,
        "response": summarise_response(event.get("tool_response")),
    }
    path = log_path(event)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError as exc:
        sys.stderr.write(f"tool-call log skipped: {exc.strerror}\n")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
