import json

from blackbox.stream import Stream, parse_line
from conftest import FIXTURES


def load_sample():
    lines = (FIXTURES / "stream-json-sample.jsonl").read_text().splitlines()
    return Stream.from_events([parse_line(l) for l in lines])


def test_real_sample_shapes():
    s = load_sample()
    assert s.init["subtype"] == "init" and s.cli_version
    assert [t.name for t in s.tool_uses] == ["Read", "Bash"]
    assert s.tool_uses[1].command == "ls -la"
    assert [r.tool_use_id for r in s.tool_results] == [t.id for t in s.tool_uses]
    assert s.result["subtype"] == "success"
    assert s.turns() == 3
    assert s.cost() > 0
    u = s.usage()
    assert u["output_tokens"] > 0 and u["cache_read_tokens"] > 0
    assert s.final_text == "hello from fixture"
    assert s.permission_denials() == []
    assert s.session_id


def test_usage_without_result_dedupes_messages():
    msg = {"id": "m1", "usage": {"input_tokens": 2, "output_tokens": 5, "cache_read_input_tokens": 7}}
    events = [{"type": "assistant", "message": {**msg, "content": [{"type": "tool_use", "id": "a", "name": "Read", "input": {}}]}},
              {"type": "assistant", "message": {**msg, "content": [{"type": "tool_use", "id": "b", "name": "Read", "input": {}}]}},
              {"type": "assistant", "message": {"id": "m2", "usage": {"output_tokens": 1}, "content": "hi"}}]
    s = Stream.from_events(events)
    assert s.usage() == {"input_tokens": 2, "output_tokens": 6, "cache_read_tokens": 7, "cache_creation_tokens": 0}
    assert s.turns() == 2
    assert s.cost() is None
    assert s.final_text == "hi"
    assert s.tool_counts() == {"Read": 2}


def test_parse_line_malformed():
    assert parse_line("{bad")["type"] == "malformed"
    assert parse_line("[1]")["type"] == "malformed"
    assert parse_line(json.dumps({"type": "x"})) == {"type": "x"}


def test_denial_from_tool_result_only():
    events = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t", "name": "Bash", "input": {"command": "rm -rf x"}}]}},
              {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t", "is_error": True,
                                                         "content": [{"type": "text", "text": "Permission to use Bash has been denied."}]}]}}]
    d = Stream.from_events(events).permission_denials()
    assert d == [{"tool_name": "Bash", "tool_use_id": "t", "tool_input": {"command": "rm -rf x"}, "event": 1}]


def _bash_then(result_block, meta=None):
    user = {"type": "user", "message": {"content": [result_block]}}
    if meta:
        user["tool_result_meta"] = [meta]
    return Stream.from_events([
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t", "name": "Bash", "input": {"command": "git push"}}]}},
        user])


def test_real_denial_sample():
    lines = (FIXTURES / "stream-json-denial-sample.jsonl").read_text().splitlines()
    s = Stream.from_events([parse_line(l) for l in lines])
    res = s.tool_results[0]
    assert res.is_error and res.decision == {"decision": "reject", "source": "config", "reason_type": "rule"}
    assert res.is_denial and not res.is_hook_block
    d = s.permission_denials()
    assert len(d) == 1 and d[0]["tool_name"] == "Read" and d[0]["event"] == 1
    assert s.hook_blocks() == []


def test_real_sandboxed_sample():
    lines = (FIXTURES / "stream-json-sandboxed-sample.jsonl").read_text().splitlines()
    s = Stream.from_events([parse_line(l) for l in lines])
    assert s.result["subtype"] == "success" and s.blocks() == []
    assert any(t.is_test_run for t in s.tool_uses)


def test_hook_block_by_text_and_by_decision():
    text_only = _bash_then({"type": "tool_result", "tool_use_id": "t", "is_error": True,
                            "content": "PreToolUse:Bash hook error: Blocked by guard: pushing."})
    assert text_only.permission_denials() == [] and text_only.hook_blocks()[0]["event"] == 1
    by_meta = _bash_then({"type": "tool_result", "tool_use_id": "t", "is_error": True, "content": "no"},
                         {"id": "t", "permission_decision": {"decision": "reject", "source": "hook"}})
    assert by_meta.hook_blocks() and not by_meta.permission_denials()
    rule = _bash_then({"type": "tool_result", "tool_use_id": "t", "is_error": True, "content": "nope"},
                      {"id": "t", "permission_decision": {"decision": "reject", "source": "config"}})
    assert rule.permission_denials()[0]["event"] == 1 and not rule.hook_blocks()
    assert [b["tool_use_id"] for b in rule.blocks()] == ["t"]
