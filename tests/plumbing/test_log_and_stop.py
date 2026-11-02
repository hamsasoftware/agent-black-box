import json

import pytest

SECRET = "sk-ant-" + "a1B2" * 10


@pytest.fixture
def log_file(tmp_path):
    return tmp_path / "logs" / "calls.jsonl"


def post_event(tool, session="s-1", **tool_input):
    return {
        "session_id": session,
        "hook_event_name": "PostToolUse",
        "tool_name": tool,
        "tool_use_id": "toolu_1",
        "tool_input": tool_input,
        "tool_response": {"stdout": "ok", "is_error": False},
    }


def test_log_appends_redacted_line(run_hook, log_file):
    env = {"TOOL_CALL_LOG": str(log_file)}
    first = run_hook("log_tool_call.py", post_event("Bash", command=f"export SERVICE_API_KEY={SECRET}"), env=env)
    second = run_hook("log_tool_call.py", post_event("Read", file_path="README.md"), env=env)
    assert first.code == 0 and second.code == 0
    lines = log_file.read_text().splitlines()
    assert len(lines) == 2
    record = json.loads(lines[0])
    assert record["tool_name"] == "Bash"
    assert record["session_id"] == "s-1"
    assert record["response"] == {"chars": len(json.dumps({"stdout": "ok", "is_error": False})), "is_error": False}
    assert SECRET not in log_file.read_text()
    assert "[REDACTED:" in record["tool_input"]


@pytest.mark.parametrize("secret", [
    "ghp_" + "x" * 36,
    "AKIA" + "ABCDEFGHIJKLMNOP",
    "Bearer " + "t" * 30,
    "-----BEGIN " + "PRIVATE KEY-----\nabc\n-----END " + "PRIVATE KEY-----",
])
def test_log_redacts_common_secrets(run_hook, log_file, secret):
    result = run_hook("log_tool_call.py", post_event("Write", file_path="x", content=secret), env={"TOOL_CALL_LOG": str(log_file)})
    assert result.code == 0
    assert secret not in log_file.read_text()


def test_log_truncates_large_input(run_hook, log_file):
    result = run_hook("log_tool_call.py", post_event("Write", file_path="x", content="y" * 10000), env={"TOOL_CALL_LOG": str(log_file)})
    assert result.code == 0
    record = json.loads(log_file.read_text())
    assert len(record["tool_input"]) < 2100
    assert "[truncated" in record["tool_input"]


def test_log_defaults_to_project_logs_dir(run_hook, project):
    result = run_hook("log_tool_call.py", post_event("Read", file_path="README.md"))
    assert result.code == 0
    assert (project / ".claude" / "logs" / "tool-calls.jsonl").is_file()


@pytest.mark.parametrize("raw", ["", "{bad", "42"])
def test_log_malformed_is_non_blocking(run_hook, log_file, raw):
    result = run_hook("log_tool_call.py", raw=raw, env={"TOOL_CALL_LOG": str(log_file)})
    assert result.code == 1
    assert "tool-call log skipped" in result.stderr
    assert not log_file.exists()


def stop_event(session="s-1", active=False):
    return {"session_id": session, "hook_event_name": "Stop", "stop_hook_active": active}


def write_log(log_file, *records):
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text("".join(json.dumps(r) + "\n" for r in records) + "not json\n")


def test_stop_reminds_after_edits(run_hook, log_file):
    write_log(log_file, {"session_id": "s-1", "tool_name": "Edit"})
    result = run_hook("stop_reminder.py", stop_event(), env={"TOOL_CALL_LOG": str(log_file)})
    assert result.code == 2
    assert "definition of done" in result.stderr
    assert "make scan" in result.stderr


def test_stop_allows_when_already_reminded(run_hook, log_file):
    write_log(log_file, {"session_id": "s-1", "tool_name": "Edit"})
    result = run_hook("stop_reminder.py", stop_event(active=True), env={"TOOL_CALL_LOG": str(log_file)})
    assert result.code == 0
    assert result.stderr == ""


@pytest.mark.parametrize("records", [
    [],
    [{"session_id": "s-1", "tool_name": "Read"}],
    [{"session_id": "other", "tool_name": "Write"}],
])
def test_stop_allows_without_edits_in_session(run_hook, log_file, records):
    write_log(log_file, *records)
    result = run_hook("stop_reminder.py", stop_event(), env={"TOOL_CALL_LOG": str(log_file)})
    assert result.code == 0


def test_stop_allows_without_log(run_hook, log_file):
    result = run_hook("stop_reminder.py", stop_event(), env={"TOOL_CALL_LOG": str(log_file)})
    assert result.code == 0


@pytest.mark.parametrize("raw", ["", "nope", "[]"])
def test_stop_malformed_is_non_blocking(run_hook, raw):
    result = run_hook("stop_reminder.py", raw=raw)
    assert result.code == 1
    assert "stop reminder skipped" in result.stderr
