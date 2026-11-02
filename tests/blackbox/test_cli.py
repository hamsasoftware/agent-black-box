import json
import os
import subprocess
import sys

from blackbox import schema
from blackbox.cli import main
from conftest import FIXTURES


def test_cli_run_and_validate(root, task_dir, env_file, monkeypatch, capsys):
    monkeypatch.setenv("FAKE_AGENT_SCENARIO", "success")
    code = main(["run", str(task_dir), "--variant", "bare", "--model", "claude-sonnet-5-5", "--budget-usd", "0.75",
                 "--root", str(root), "--env-file", str(env_file), "--agent-cli", str(FIXTURES / "fake_agent.py")])
    assert code == 0
    run_dir = capsys.readouterr().out.strip()
    assert run_dir.startswith(str(root / "runs"))
    assert main(["validate", "--root", str(root)]) == 0
    assert main(["scan", str(root)]) == 0
    assert main(["scan", "--env-file", str(env_file), str(root)]) == 0
    rec_path = next((root / "runs").glob("*/run.json"))
    rec = json.loads(rec_path.read_text())
    rec["variant"] = "weird"
    del rec["turns"]
    rec_path.write_text(json.dumps(rec))
    capsys.readouterr()
    assert main(["validate", str(rec_path)]) == 1
    out = capsys.readouterr().out
    assert "missing turns" in out and "variant" in out
    (root / "ledger" / "agents.jsonl").write_text("{\nnot json\n" + json.dumps({"agent_id": "bad"}) + "\n")
    assert main(["validate", str(root / "ledger")]) == 1


def test_cli_run_error(root, task_dir, tmp_path, capsys):
    code = main(["run", str(task_dir), "--variant", "plumbed", "--model", "m", "--root", str(root),
                 "--env-file", str(tmp_path / "missing.env")])
    assert code == 2
    assert "env file" in capsys.readouterr().err


def test_scan_finds(tmp_path, capsys):
    (tmp_path / "x.txt").write_text("ghp_" + "Q" * 36 + "\n")
    assert main(["scan", str(tmp_path)]) == 1
    assert "github-token" in capsys.readouterr().out


def test_module_entry_point(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(FIXTURES.parents[2] / "src")}
    proc = subprocess.run([sys.executable, "-m", "blackbox", "scan", str(tmp_path)], capture_output=True, text=True, env=env)
    assert proc.returncode == 0


def test_schema_file_is_valid_json():
    s = schema.load_schema()
    assert set(s["$defs"]) >= {"run", "agent"}
    assert schema.validate(5, {"type": "integer", "minimum": 6}, s) == ["$: below 6"]
    assert schema.validate("x", {"anyOf": [{"type": "integer"}, {"type": "null"}]}, s)
    assert schema.validate({"a": 1}, {"type": "object", "additionalProperties": False}, s) == ["$: unexpected a"]
    assert schema.validate(2.0, {"type": "number", "maximum": 1}, s) == ["$: above 1"]


def test_grader_without_result(do_run, task_dir):
    (task_dir / "grader" / "run.py").write_text("import sys\nprint('no json here')\nsys.exit(4)\n")
    _, rec, _ = do_run("success")
    assert rec["grade"]["passed"] is False and "exit 4" in rec["grade"]["error"]
    assert rec["stop_reason"] == "success"


def test_cli_task_id(root, task_dir, env_file, capsys):
    import shutil
    shutil.copytree(task_dir, root / "tasks" / "demo-add")
    code = main(["run", "--task", "demo-add", "--variant", "bare", "--model", "m", "--sandbox", "off",
                 "--root", str(root), "--env-file", str(env_file), "--agent-cli", str(FIXTURES / "fake_agent.py")])
    assert code == 0 and "demo-add-bare" in capsys.readouterr().out
    assert main(["run", "--variant", "bare", "--model", "m", "--root", str(root)]) == 2
