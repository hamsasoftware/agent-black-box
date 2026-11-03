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


def test_an_unpinned_task_is_recorded_as_version_one_without_a_protocol(do_run, task_dir):
    from blackbox import taskspec
    _, rec, argv = do_run("success")
    assert rec["task_version"] == 1 and rec["protocol_version"] is None and rec["phase"] is None
    assert rec["task_sha256"] == taskspec.task_sha256(task_dir)
    assert rec["harness_commit"] is None, "the test root is not a git checkout"
    assert "Rules for this task" not in argv["argv"][1]
    assert schema.validate_run(rec, json.loads((FIXTURES.parents[2] / "schemas" / "ledger.schema.json").read_text())) == []


def test_a_pinned_task_sends_its_rules_and_records_the_protocol(do_run, task_dir):
    import hashlib
    spec = task_dir / "task.yaml"
    spec.write_text(spec.read_text().rstrip("\n") + '\nversion: 2\nrules:\n  - id: scope\n    text: "Change only calc.py."\n')
    _, rec, argv = do_run("success")
    sent = argv["argv"][1]
    assert sent.startswith("Fix the bug") and sent.rstrip().endswith("- Change only calc.py.")
    assert "Rules for this task:" in sent
    assert rec["prompt_sha256"] == hashlib.sha256(sent.encode()).hexdigest()
    assert rec["task_version"] == 2 and rec["protocol_version"] is None and rec["phase"] is None, "no --phase: exploratory"


def test_harness_commit_names_the_commit_and_flags_local_changes(tmp_path):
    import subprocess
    from blackbox.runner import harness_commit
    assert harness_commit(tmp_path) is None
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@localhost", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@localhost",
           "PATH": __import__("os").environ["PATH"], "HOME": str(tmp_path)}
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, env=env, check=True, capture_output=True)
    git("init", "-q")
    (tmp_path / "f.txt").write_text("one")
    git("add", "f.txt")
    git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "first")
    clean = harness_commit(tmp_path)
    assert re.fullmatch(r"[0-9a-f]{40}", clean)
    (tmp_path / "f.txt").write_text("two")
    assert harness_commit(tmp_path) == clean + "+dirty"
    (tmp_path / "untracked.txt").write_text("x")
    git("checkout", "--", "f.txt")
    assert harness_commit(tmp_path) == clean, "untracked files do not make the checkout dirty"


def test_harness_commit_ignores_the_harness_own_output_but_not_source(tmp_path):
    import subprocess
    from blackbox.runner import harness_commit
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@localhost", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@localhost",
           "PATH": __import__("os").environ["PATH"], "HOME": str(tmp_path)}
    repo = tmp_path / "r"
    for d in ("ledger", "runs", "src", "tests", "tasks", "schemas", "docs", "scripts"):
        (repo / d).mkdir(parents=True)
        (repo / d / "f.txt").write_text("one")
    def git(*args):
        subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)
    git("init", "-q")
    git("add", "-A")
    git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "first")
    clean = harness_commit(repo)
    assert re.fullmatch(r"[0-9a-f]{40}", clean)
    (repo / "ledger" / "f.txt").write_text("two")
    (repo / "runs" / "f.txt").write_text("two")
    assert harness_commit(repo) == clean, "rewriting ledger/ and runs/ files is the harness's own output"
    for d in ("src", "tests", "tasks", "schemas", "docs", "scripts"):
        (repo / d / "f.txt").write_text("two")
        assert harness_commit(repo) == clean + "+dirty", d
        git("checkout", "--", f"{d}/f.txt")
        assert harness_commit(repo) == clean
    (repo / "src" / "f.txt").write_text("two")
    (repo / "ledger" / "f.txt").write_text("three")
    assert harness_commit(repo) == clean + "+dirty", "source changes still count next to harness output"


def test_consecutive_runs_do_not_record_dirty_from_their_own_ledger_writes(do_run, root):
    import subprocess
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@localhost", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@localhost",
           "PATH": __import__("os").environ["PATH"], "HOME": str(root)}
    (root / "ledger").mkdir()
    (root / "ledger" / "agents.jsonl").write_text("")
    (root / "runs").mkdir(exist_ok=True)
    (root / "runs" / "index.jsonl").write_text("")
    def git(*args):
        subprocess.run(["git", *args], cwd=root, env=env, check=True, capture_output=True)
    git("init", "-q")
    git("add", "-A")
    git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "first")
    commits = [do_run("success")[1]["harness_commit"] for _ in range(3)]
    assert all(re.fullmatch(r"[0-9a-f]{40}", c) for c in commits), commits
    assert (root / "ledger" / "agents.jsonl").read_text(), "the ledger was rewritten between the runs"


# ---- --phase ----------------------------------------------------------------------------------------------------------

def phase_setup(root, task_dir, *, frozen=True, lock=True, manifest=True, version=2, models=("claude-sonnet-5-5",), variants=("bare",)):
    """Make the demo task a frozen v2 task, lock it, and write a valid manifest for phase 1 under `root`."""
    from blackbox import phase, taskspec
    spec = task_dir / "task.yaml"
    spec.write_text(spec.read_text().rstrip("\n") + f"\nversion: {version}\nfrozen: {'true' if frozen else 'false'}\n")
    sha = taskspec.task_sha256(task_dir)
    (root / "tasks").mkdir(exist_ok=True)
    (root / "tasks" / "LOCK.json").write_text(json.dumps({"protocol": 1, "tasks": {"demo-add": {"version": version, "sha256": sha}} if lock else {}}))
    if manifest:
        (root / "schemas").mkdir(exist_ok=True)
        (root / "schemas" / "phase-manifest.schema.json").write_text((FIXTURES.parents[2] / "schemas" / "phase-manifest.schema.json").read_text())
        m = {"protocol_version": 1, "phase": 1, "questions": ["Q1"], "models": list(models), "variants": list(variants), "plumbed_model": None,
             "tasks": {"demo-add": {"version": version, "sha256": sha}}, "repeats": 2, "harness_commit": "0" * 40, "seed": 5,
             "shuffle": phase.SHUFFLE, "budget_usd": 5.0, "runs": []}
        m["runs"] = phase.expected_runs(m)
        (root / "protocol").mkdir(exist_ok=True)
        (root / "protocol" / "phase-1.json").write_text(json.dumps(m))
    return sha


def test_a_candidate_task_run_is_exploratory(do_run, root, task_dir):
    phase_setup(root, task_dir, frozen=False, lock=False, manifest=False)
    _, rec, _ = do_run("success")
    assert rec["task_version"] == 2 and rec["protocol_version"] is None and rec["phase"] is None


def test_a_frozen_locked_task_without_phase_is_still_exploratory(do_run, root, task_dir):
    phase_setup(root, task_dir)
    _, rec, _ = do_run("success")
    assert rec["protocol_version"] is None and rec["phase"] is None


def test_a_valid_phase_run_is_stamped_with_the_protocol_and_the_phase(do_run, root, task_dir):
    phase_setup(root, task_dir)
    _, rec, _ = do_run("success", phase=1)
    assert rec["protocol_version"] == 1 and rec["phase"] == 1
    assert schema.validate_run(rec, json.loads((FIXTURES.parents[2] / "schemas" / "ledger.schema.json").read_text())) == []
    from blackbox import report
    assert report.index_row(rec)["phase"] == 1


@pytest.mark.parametrize("setup, needle", [
    (dict(frozen=False, lock=False), "candidate"),
    (dict(lock=False), "not in tasks/LOCK.json"),
    (dict(manifest=False), "does not exist"),
    (dict(models=("claude-haiku-4-5-20251001",)), "model claude-sonnet-5-5 is not in the manifest"),
])
def test_phase_is_refused_before_anything_runs(do_run, root, task_dir, setup, needle):
    phase_setup(root, task_dir, **setup)
    with pytest.raises(HarnessError, match=needle):
        do_run("success", phase=1)
    assert not (root / "runs").exists() and not (root / "ledger").exists(), "nothing ran and nothing was written"


def test_phase_is_refused_for_an_invalid_manifest(do_run, root, task_dir):
    phase_setup(root, task_dir)
    path = root / "protocol" / "phase-1.json"
    m = json.loads(path.read_text())
    m["runs"].pop()
    path.write_text(json.dumps(m))
    with pytest.raises(HarnessError, match="missing"):
        do_run("success", phase=1)
    path.write_text("{not json")
    with pytest.raises(HarnessError, match="cannot be read"):
        do_run("success", phase=1)


def test_phase_is_refused_for_a_variant_not_in_the_manifest(do_run, root, task_dir):
    phase_setup(root, task_dir)
    with pytest.raises(HarnessError, match="variant plumbed"):
        do_run("success", variant="plumbed", phase=1)


def test_phase_is_refused_for_another_phase_or_a_task_that_changed_since_the_lock(do_run, root, task_dir):
    phase_setup(root, task_dir)
    with pytest.raises(HarnessError, match="phase-2.json does not exist"):
        do_run("success", phase=2)
    (task_dir / "PROMPT.md").write_text("edited after the lock\n")
    with pytest.raises(HarnessError, match="differs from tasks/LOCK.json"):
        do_run("success", phase=1)
