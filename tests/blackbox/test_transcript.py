import json

from blackbox import schema
from blackbox.cli import main
from conftest import FAKE_KEY


def line(obj):
    return json.dumps(obj) + "\n"


def write_transcript(path):
    base = {"agentId": "abc123", "sessionId": "s1", "cwd": "/home/alice/repo"}
    path.write_text(
        line({**base, "type": "user", "timestamp": "2026-11-02T10:00:00.000Z",
              "message": {"role": "user", "content": "Build the harness. Contact dev" + "@" + "example.com " + "x" * 600}})
        + line({**base, "type": "attachment", "timestamp": "2026-11-02T10:00:01.000Z", "attachment": {"type": "skill_listing", "content": "secret stuff"}})
        + line({**base, "type": "api-request", "timestamp": "2026-11-02T10:00:01.500Z", "params": {"k": FAKE_KEY}})
        + "{not json\n"
        + line({**base, "type": "assistant", "timestamp": "2026-11-02T10:00:02.000Z", "message": {
            "model": "claude-opus-5-5", "id": "m1", "role": "assistant",
            "usage": {"input_tokens": 10, "output_tokens": 20, "cache_read_input_tokens": 30, "cache_creation_input_tokens": 40},
            "content": [{"type": "thinking", "thinking": "hmm"},
                        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": f"export K={FAKE_KEY}; gh pr merge 1", "timeout": 5}}]}})
        + line({**base, "type": "assistant", "timestamp": "2026-11-02T10:00:02.100Z", "message": {
            "model": "claude-opus-5-5", "id": "m1", "role": "assistant",
            "usage": {"input_tokens": 10, "output_tokens": 20, "cache_read_input_tokens": 30, "cache_creation_input_tokens": 40},
            "content": [{"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": "/home/alice/repo/x.py", "opts": {"a": 1}}}]}})
        + line({**base, "type": "user", "timestamp": "2026-11-02T10:00:03.000Z", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "is_error": True, "content": "Permission for this action was denied by the auto mode classifier."},
            {"type": "tool_result", "tool_use_id": "t2", "content": [{"type": "text", "text": "print(1)"}]}]}})
        + line({**base, "type": "assistant", "timestamp": "2026-11-02T10:01:00.000Z", "message": {
            "model": "claude-opus-5-5", "id": "m2", "role": "assistant", "usage": {"input_tokens": 1, "output_tokens": 2},
            "content": [{"type": "text", "text": "See https://github.com/other/repo/pull/9"},
                        {"type": "tool_use", "id": "t3", "name": "Bash", "input": {"command": "gh pr create -R hexrift/agent-black-box"}}]}})
        + line({**base, "type": "user", "timestamp": "2026-11-02T10:01:00.000Z", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t3", "content": "https://github.com/hexrift/agent-black-box/pull/7"}]}})
    )


def test_ingest(tmp_path):
    src = tmp_path / "t.output"
    write_transcript(src)
    root = tmp_path / "repo"
    env = tmp_path / "e.env"
    env.write_text(f"ANTHROPIC_API_KEY={FAKE_KEY}\n")
    for _ in range(2):
        assert main(["ingest-transcript", str(src), "--name", "Tally", "--role", "harness", "--root", str(root),
                     "--env-file", str(env), "--outcome", "pr-open"]) == 0
    agents = [json.loads(l) for l in (root / "ledger" / "agents.jsonl").read_text().splitlines()]
    assert len(agents) == 1
    a = agents[0]
    assert a["kind"] == "builder" and a["name"] == "Tally" and a["role"] == "harness"
    assert a["model"] == "claude-opus-5-5"
    assert a["tokens"] == {"input": 11, "output": 22, "cache_read": 30, "cache_creation": 40}
    assert a["tool_uses"] == 3 and a["tool_calls"] == {"Bash": 2, "Read": 1}
    assert a["duration_ms"] == 60000
    assert a["pr"] == "https://github.com/hexrift/agent-black-box/pull/7"
    assert a["malformed_lines"] == 1
    assert a["blocked_actions"][0]["tool"] == "Bash"
    assert schema.validate_agent(a, schema.load_schema()) == []
    events_text = (root / "ledger" / "builders" / "Tally" / "events.jsonl").read_text()
    events = [json.loads(l) for l in events_text.splitlines()]
    assert {e["agent_id"] for e in events} == {a["agent_id"]}
    assert [e["kind"] for e in events] == ["text", "skill_listing", "thinking", "tool_use", "tool_use", "tool_result", "tool_result", "text", "tool_use", "tool_result"]
    assert FAKE_KEY not in events_text and "example.com" not in events_text and "alice" not in events_text
    assert "secret stuff" not in events_text and "hmm" not in events_text
    assert "more chars" in events[0]["text"]
