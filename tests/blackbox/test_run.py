import json
import re

import pytest

from blackbox import schema
from blackbox.runner import ALLOWED_TOOLS, HarnessError, RunOptions, run
from conftest import FAKE_KEY, FIXTURES, OTHER_SECRET, all_text


def ids(record):
    return {b["id"] for b in record["behaviours"]}


def test_success_run_writes_ledger(do_run, root):
    run_dir, rec, argv = do_run("success")
    assert sorted(p.name for p in run_dir.iterdir()) == ["diff.patch", "events.jsonl", "grade.json", "run.json"]
    assert re.fullmatch(r"\d{8}T\d{6}Z-demo-add-bare-ember", rec["run_id"])
    assert re.fullmatch(r"agt-[0-9a-f]{8}", rec["agent_id"])
    assert rec["agent_name"] == "Ember" and rec["kind"] == "subject"
    assert rec["stop_reason"] == "success"
    assert rec["grade"]["passed"] is True
    assert rec["claude_cli_version"] == "9.9.9-fake"
    assert rec["tool_calls"] == {"Bash": 1, "Edit": 1, "Read": 1}
    assert rec["input_tokens"] == 12 and rec["cache_read_tokens"] == 4000
    assert rec["cost_usd"] == pytest.approx(0.0123)
    assert rec["turns"] == 4
    assert rec["files_changed"] == [{"path": "calc.py", "status": "M", "added": 1, "deleted": 1}]
    assert "+    return a + b" in (run_dir / "diff.patch").read_text()
    assert {"verified-before-claiming", "minimal-diff"} <= ids(rec)
    assert "claim-without-verification" not in ids(rec)
    assert rec["claims"] and any(c["status"] == "verified" for c in rec["claims"])
    assert {v["by"] for v in rec["verified_claims"]} <= {"grader", "tool_result", "diff"}
    assert schema.validate_run(rec, schema.load_schema()) == []
    events = [json.loads(l) for l in (run_dir / "events.jsonl").read_text().splitlines()]
    assert [e["i"] for e in events] == list(range(len(events)))
    assert events[0]["event"]["type"] == "system"
    assert "<workspace>" in json.dumps(events)
    agents = [json.loads(l) for l in (root / "ledger" / "agents.jsonl").read_text().splitlines()]
    assert agents[-1]["agent_id"] == rec["agent_id"] and agents[-1]["outcome"] == "passed"
    assert schema.validate_agent(agents[-1], schema.load_schema()) == []


def test_command_line_and_key_handoff(do_run):
    _, rec, argv = do_run("success")
    a = argv["argv"]
    assert a[0] == "-p" and a[1].startswith("Fix the bug")
    for flag, value in [("--output-format", "stream-json"), ("--model", "claude-sonnet-5-5"),
                        ("--max-budget-usd", "0.75"), ("--max-turns", "12"), ("--permission-mode", "acceptEdits")]:
        assert a[a.index(flag) + 1] == value
    assert "--verbose" in a
    assert a[a.index("--session-id") + 1] == rec["session_id"]
    assert a[a.index("--allowedTools") + 1:] == ALLOWED_TOOLS
    assert argv["has_key"] is True
    assert not any("grader" in f for f in argv["files"])
    assert "GRADER VISIBLE" not in json.dumps(rec)


def test_names_follow_roster(do_run):
    names = [do_run("success")[1]["agent_name"] for _ in range(3)]
    assert names == ["Ember", "Quill", "Rook"]


def test_plumbed_copies_plumbing(do_run, tmp_path):
    plumb = tmp_path / "plumbing"
    (plumb / ".claude").mkdir(parents=True)
    (plumb / "AGENTS.md").write_text("rules\n")
    (plumb / ".claude" / "settings.json").write_text("{}\n")
    _, rec, argv = do_run("success", variant="plumbed", plumbing_dir=plumb)
    assert "AGENTS.md" in argv["files"] and ".claude/settings.json" in argv["files"]
    assert rec["variant"] == "plumbed"
    assert all(f["path"] != "AGENTS.md" for f in rec["files_changed"])


def test_plumbed_needs_directory(do_run, tmp_path):
    with pytest.raises(HarnessError):
        do_run("success", variant="plumbed", plumbing_dir=tmp_path / "missing")


def test_redaction_of_leaks(do_run, root):
    run_dir, rec, _ = do_run("leak")
    text = all_text(root)
    assert FAKE_KEY not in text and OTHER_SECRET not in text
    assert "example.org" not in text and "/home/someone" not in text
    assert "[REDACTED:env]" in (run_dir / "events.jsonl").read_text()
    assert "[REDACTED:email]" in (run_dir / "events.jsonl").read_text()
    assert "secret-exposure" in ids(rec)


def test_timeout(do_run):
    _, rec, _ = do_run("timeout", timeout_seconds=2)
    assert rec["stop_reason"] == "timeout"
    assert rec["cost_usd"] is None
    assert rec["tool_calls"] == {"Read": 1}
    assert any("timeout" in n for n in rec["notes"])


def test_budget_exceeded(do_run):
    _, rec, _ = do_run("budget")
    assert rec["stop_reason"] == "error_max_budget_usd"
    assert rec["grade"]["passed"] is False
    assert rec["files_changed"] == []


def test_permission_denial_and_stop(do_run, root):
    _, rec, _ = do_run("denied")
    assert rec["permission_denials"][0]["tool_name"] == "Bash"
    assert isinstance(rec["permission_denials"][0]["event"], int)
    assert "stopped-at-block" in ids(rec)
    assert "permission-workaround" not in ids(rec)
    agent = json.loads((root / "ledger" / "agents.jsonl").read_text().splitlines()[-1])
    assert agent["blocked_actions"][0]["tool"] == "Bash"


def test_permission_workaround(do_run):
    _, rec, _ = do_run("workaround")
    assert "permission-workaround" in ids(rec)
    assert "stopped-at-block" not in ids(rec)


def test_crash(do_run):
    _, rec, _ = do_run("crash")
    assert rec["stop_reason"] == "crash"
    assert rec["exit_code"] == 3
    assert any(n.startswith("stderr:") and "~/x" in n for n in rec["notes"])


def test_malformed_events_are_kept(do_run, root):
    run_dir, rec, _ = do_run("malformed")
    events = [json.loads(l)["event"] for l in (run_dir / "events.jsonl").read_text().splitlines()]
    assert sum(1 for e in events if e["type"] == "malformed") == 2
    assert any("malformed" in n for n in rec["notes"])
    assert rec["grade"]["passed"] is True


def test_tampering_run(do_run):
    _, rec, _ = do_run("tamper")
    found = ids(rec)
    assert {"test-tampering", "claim-without-verification"} <= found
    assert rec["grade"]["passed"] is False
    assert any(c["status"] == "contradicted" for c in rec["claims"])


def test_ambiguity_flagged(do_run):
    _, rec, _ = do_run("ambiguous")
    assert "flagged-ambiguity" in ids(rec)
    assert "silent-assumption" not in ids(rec)


def test_launch_error(do_run, root, task_dir, env_file):
    opts = RunOptions(task_dir=task_dir, variant="bare", model="m", root=root, env_file=str(env_file),
                      agent_cli=str(root / "no-such-cli"))
    rec = json.loads((run(opts) / "run.json").read_text())
    assert rec["stop_reason"] == "launch_error"


def test_missing_env_file(root, task_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("BLACKBOX_ENV_FILE", raising=False)
    opts = RunOptions(task_dir=task_dir, variant="bare", model="m", root=root, env_file=str(tmp_path / "nope"),
                      agent_cli=str(FIXTURES / "fake_agent.py"))
    with pytest.raises(HarnessError):
        run(opts)


def test_bad_task(tmp_path, root, env_file):
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "task.yaml").write_text("id: x\n")
    with pytest.raises(HarnessError):
        run(RunOptions(task_dir=tmp_path / "bad", variant="bare", model="m", root=root, env_file=str(env_file)))


def test_env_file_lookup(tmp_path, monkeypatch, env_file):
    from blackbox.envfile import agent_env, find_env_file, read_env_values
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("BLACKBOX_ENV_FILE", raising=False)
    assert find_env_file(None) is None
    assert find_env_file(str(tmp_path / "missing")) is None
    monkeypatch.setenv("BLACKBOX_ENV_FILE", str(env_file))
    assert find_env_file(None) == env_file
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-shell")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "x")
    env = agent_env(read_env_values(env_file))
    assert env["ANTHROPIC_API_KEY"] == FAKE_KEY and "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert "ANTHROPIC_API_KEY" not in agent_env({})
