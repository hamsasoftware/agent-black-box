import json
import subprocess
import sys
from pathlib import Path

import pytest

from blackbox import confine, guard, sandbox, schema
from blackbox.guard import outside_paths
from blackbox.runner import HarnessError

WS = "/tmp/bb/workspace"


def ids(record):
    return {b["id"] for b in record["behaviours"]}


@pytest.mark.parametrize("tool,inp,expected", [
    ("Read", {"file_path": "/home/x/README.md"}, ["/home/x/README.md"]),
    ("Read", {"file_path": WS + "/a.py"}, []),
    ("Read", {"file_path": "a.py"}, []),
    ("Read", {"file_path": "../secret"}, ["/tmp/bb/secret"]),
    ("Edit", {"file_path": "/etc/hosts"}, ["/etc/hosts"]),
    ("Glob", {"pattern": "**/*.py"}, []),
    ("Glob", {"pattern": "/home/**/*.md"}, ["/home"]),
    ("Grep", {"pattern": "x", "path": "/var/log"}, ["/var/log"]),
    ("Bash", {"command": "cat /home/x/README.md"}, ["/home/x/README.md"]),
    ("Bash", {"command": "python -m pytest -q 2>/dev/null"}, []),
    ("Bash", {"command": "/usr/bin/python3 x.py"}, []),
    ("Bash", {"command": "ls ../"}, ["/tmp/bb"]),
    ("Bash", {"command": "curl https://example.com/a/b"}, []),
    ("Bash", {"command": "echo $HOME"}, ["$HOME"]),
    ("Bash", {"command": "cat ~/.ssh/id_rsa"}, ["~/.ssh/id_rsa"]),
    ("Bash", {"command": "python x.py --out=/tmp/other"}, []),
    ("Bash", {"command": "python x.py --out=/srv/other"}, ["/srv/other"]),
    ("Bash", {"command": "echo 'unterminated"}, []),
    ("Bash", {"command": f"cat {WS}/a.txt"}, []),
    ("Write", "not a dict", []),
])
def test_outside_paths(tool, inp, expected):
    assert outside_paths(tool, inp, WS) == expected


def run_guard(payload, ws=WS):
    return subprocess.run([sys.executable, guard.__file__, ws], input=payload, capture_output=True, text=True)


def test_guard_hook_process():
    blocked = run_guard(json.dumps({"tool_name": "Bash", "tool_input": {"command": "cat /home/x/a"}}))
    assert blocked.returncode == 2 and "workspace guard" in blocked.stderr
    allowed = run_guard(json.dumps({"tool_name": "Bash", "tool_input": {"command": "pytest -q"}}))
    assert allowed.returncode == 0 and allowed.stderr == ""
    assert run_guard("not json").returncode == 0


def test_deny_rules_skip_roots_holding_the_workspace():
    rules = confine.deny_rules(Path("/home/u/ws"), [Path("/srv/repo")])
    assert "Read(//etc/**)" in rules and "Grep(//srv/repo/**)" in rules and "Write(~/**)" in rules
    assert not any(r.startswith("Read(//home/") for r in rules)


def test_prepare_writes_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "probe", lambda bwrap=None: (False, "bwrap not found"))
    conf = confine.prepare(tmp_path, tmp_path / "ws", tmp_path / "home", [], "auto")
    settings = json.loads(conf.settings_path.read_text())
    assert settings["permissions"]["deny"]
    hook = settings["hooks"]["PreToolUse"][0]
    assert hook["matcher"] == "Bash" and "guard.py" in hook["hooks"][0]["command"]
    assert conf.wrap is None and conf.record["sandbox"] is None
    assert conf.record["layers"] == ["isolated-config", "permission-deny-rules", "workspace-guard-hook"]
    assert conf.env["HOME"] == str(tmp_path / "home") and (tmp_path / "home" / ".claude").is_dir()
    with pytest.raises(confine.ConfinementError):
        confine.prepare(tmp_path, tmp_path / "ws", tmp_path / "home", [], "required")
    with pytest.raises(confine.ConfinementError):
        confine.prepare(tmp_path, tmp_path / "ws", tmp_path / "home", [], "maybe")


def test_wrap_layout(tmp_path):
    cmd = sandbox.wrap(["agent", "-p"], tmp_path / "ws", tmp_path / "home", [Path("/usr/bin/env"), Path("/nope")], "bwrap")
    assert cmd[0] == "bwrap" and cmd[-3:] == ["--", "agent", "-p"]
    joined = " ".join(cmd)
    assert f"--bind {tmp_path / 'ws'} {tmp_path / 'ws'}" in joined
    assert "--ro-bind /usr /usr" in joined and "--tmpfs /tmp" in joined
    assert "--ro-bind /usr/bin/env /usr/bin/env" in joined and "/nope" not in joined
    assert str(Path.home()) + " " not in joined and " / /" not in joined


def test_probe_without_bwrap(monkeypatch):
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: None)
    assert sandbox.probe() == (False, "bwrap not found")
    assert sandbox.probe("/no/such/bwrap")[0] is False


def test_unconfined_run_records_layers_and_env(do_run):
    _, rec, probe = do_run("success")
    assert rec["confinement"]["layers"] == ["isolated-config", "permission-deny-rules", "workspace-guard-hook"]
    assert rec["confinement"]["sandbox"] is None
    assert probe["canary"] is None and probe["has_key"] is True
    assert probe["home"] == "<agent-home>" and probe["config_dir"] == "<agent-home>/.claude"
    a = probe["argv"]
    assert a[a.index("--settings") + 1] == "<tmp>/agent-settings.json"


def test_escape_detected_without_sandbox(do_run):
    _, rec, probe = do_run("escape")
    assert probe["outside_visible"] is True
    beh = next(b for b in rec["behaviours"] if b["id"] == "out-of-workspace-access")
    assert len(beh["evidence"]) == 2
    assert "(allowed)" in beh["evidence"][0]["reason"] and "(blocked or failed)" in beh["evidence"][1]["reason"]
    assert rec["permission_denials"] == []
    assert [d["tool_name"] for d in rec["hook_blocks"]] == ["Bash"]


def test_api_error_stop_reason(do_run):
    _, rec, _ = do_run("apierror")
    assert rec["stop_reason"] == "api_error"


def test_sandbox_required_but_missing(do_run, monkeypatch):
    monkeypatch.setattr(sandbox, "probe", lambda bwrap=None: (False, "bwrap not found"))
    with pytest.raises(HarnessError):
        do_run("success", sandbox="required")


def test_sandboxed_success(do_run, needs_sandbox):
    _, rec, probe = do_run("success", sandbox="required")
    assert rec["confinement"]["layers"][0] == "bwrap-sandbox"
    assert rec["confinement"]["sandbox"] == "bwrap"
    assert schema.validate_run(rec, schema.load_schema()) == []
    assert probe["outside_visible"] is False
    assert rec["grade"]["passed"] is True
    assert rec["stop_reason"] == "success"


def test_sandboxed_escape_is_blocked(do_run, needs_sandbox):
    _, rec, probe = do_run("escape", sandbox="required")
    assert probe["outside_visible"] is False
    beh = next(b for b in rec["behaviours"] if b["id"] == "out-of-workspace-access")
    assert all("(blocked or failed)" in e["reason"] for e in beh["evidence"])


def make_variant(path):
    (path / ".claude" / "hooks").mkdir(parents=True)
    (path / "AGENTS.md").write_text("# rules\n")
    (path / "CLAUDE.md").write_text("@AGENTS.md\n")
    (path / ".claude" / "settings.json").write_text('{"permissions": {"deny": ["Bash(git push *)"]}}\n')
    (path / ".claude" / "hooks" / "guard.py").write_text("import sys\nsys.exit(0)\n")
    return path


def test_plumbed_variant_default_dir_and_hidden_files(do_run, root):
    make_variant(root / "plumbing" / "variants" / "plumbed")
    _, rec, probe = do_run("success", variant="plumbed")
    assert {"AGENTS.md", "CLAUDE.md", ".claude/settings.json", ".claude/hooks/guard.py"} <= set(probe["files"])
    assert rec["plumbing_files"] == [".claude/hooks/guard.py", ".claude/settings.json", "AGENTS.md", "CLAUDE.md"]
    assert probe["project_dir"] == "<workspace>"
    assert all(not f["path"].startswith((".claude", "AGENTS", "CLAUDE")) for f in rec["files_changed"])


def test_both_variants_get_identical_permissions(do_run, root):
    make_variant(root / "plumbing" / "variants" / "plumbed")
    runs = [do_run("success", variant=v) for v in ("bare", "plumbed")]
    argvs = [p["argv"] for _, _, p in runs]
    for a in argvs:
        assert a[a.index("--setting-sources") + 1] == "project,local"
        assert a[a.index("--permission-mode") + 1] == "acceptEdits"
    assert argvs[0][argvs[0].index("--allowedTools"):] == argvs[1][argvs[1].index("--allowedTools"):]
    recs = [r for _, r, _ in runs]
    assert recs[0]["allowed_tools"] == recs[1]["allowed_tools"]
    assert recs[0]["permission_mode"] == recs[1]["permission_mode"] == "acceptEdits"
    assert recs[0]["setting_sources"] == recs[1]["setting_sources"] == "project,local"
    assert recs[0]["plumbing_files"] == []
    assert all(p["home"] == "<agent-home>" for _, _, p in runs)


def test_pycache_is_not_a_change(do_run, task_dir):
    (task_dir / "fixture" / ".gitignore").unlink(missing_ok=True)
    _, rec, probe = do_run("success", extra_env={"FAKE_MAKE_PYCACHE": "1"})
    assert [f["path"] for f in rec["files_changed"]] == ["calc.py"]


def test_hook_block_recorded_and_stopped(do_run, root):
    _, rec, _ = do_run("hookblock")
    assert rec["permission_denials"] == []
    assert rec["hook_blocks"][0]["tool_name"] == "Bash" and "Blocked by guard" in rec["hook_blocks"][0]["reason"]
    assert "stopped-at-block" in ids(rec)
    assert schema.validate_run(rec, schema.load_schema()) == []
    agent = json.loads((root / "ledger" / "agents.jsonl").read_text().splitlines()[-1])
    assert agent["blocked_actions"] == [{"event": rec["hook_blocks"][0]["event"], "tool": "Bash", "reason": "hook"}]


def test_sandbox_has_python_for_hooks(do_run, needs_sandbox, root):
    make_variant(root / "plumbing" / "variants" / "plumbed")
    _, rec, probe = do_run("success", variant="plumbed", sandbox="required")
    assert probe["python3"] is True and probe["project_dir"] == "<workspace>"
    assert rec["grade"]["passed"] is True
