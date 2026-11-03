import importlib.util
import json
from pathlib import Path

import yaml

from test_taskspec import TASK, NOTES, make

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("task_lock", ROOT / "scripts" / "task_lock.py")
task_lock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(task_lock)

PILOT = "# Pilot\n\n## v2\n\n- Verdict: approved\n"


def repo(tmp_path, frozen=True, pilot=True, version=2):
    """A root whose tasks/ holds one complete task."""
    root = tmp_path / "repo"
    task = {**TASK, "frozen": frozen, "version": version}
    notes = NOTES.replace("v2", f"v{version}")
    made = make(tmp_path / "scratch", task=task, notes=notes)
    (root / "tasks").mkdir(parents=True)
    made.rename(root / "tasks" / "t")
    (root / "tasks" / "t" / "task.yaml").write_text(yaml.safe_dump({**task, "id": "t"}))
    if pilot:
        (root / "tasks" / "t" / "PILOT.md").write_text(PILOT.replace("v2", f"v{version}"))
    return root


def run(root, command):
    return task_lock.main([command, "--root", str(root)])


def lock(root):
    return json.loads((root / "tasks" / "LOCK.json").read_text())["tasks"]


def test_a_candidate_is_not_locked_and_check_passes_without_a_lock(tmp_path):
    root = repo(tmp_path, frozen=False)
    assert run(root, "write") == 0
    assert lock(root) == {}
    assert run(root, "check") == 0


def test_freezing_records_the_version_and_hash(tmp_path):
    root = repo(tmp_path)
    assert run(root, "check") == 1, "a frozen task with no lock entry fails the check"
    assert run(root, "write") == 0
    entry = lock(root)["t"]
    assert entry["version"] == 2 and len(entry["sha256"]) == 64
    assert run(root, "check") == 0


def test_a_frozen_task_cannot_change_at_the_same_version(tmp_path, capsys):
    root = repo(tmp_path)
    assert run(root, "write") == 0
    (root / "tasks" / "t" / "PROMPT.md").write_text("Please write a summary to SUMMARY.md. Also something new.")
    assert run(root, "check") == 1
    assert "changed without a new version" in capsys.readouterr().err
    assert run(root, "write") == 1, "write refuses to overwrite a changed task at the same version"


def test_raising_the_version_requires_a_new_pilot_and_then_refreezes(tmp_path, capsys):
    root = repo(tmp_path)
    assert run(root, "write") == 0
    path = root / "tasks" / "t" / "task.yaml"
    data = yaml.safe_load(path.read_text())
    data["version"] = 3
    path.write_text(yaml.safe_dump(data))
    notes = root / "tasks" / "t" / "NOTES.md"
    notes.write_text(notes.read_text().rstrip("\n") + "\n- v3 (2026-11-04): changed.\n")
    assert run(root, "check") == 1
    assert "newer than the lock" in capsys.readouterr().err
    assert run(root, "write") == 1
    assert "no approved review for v3" in capsys.readouterr().err
    (root / "tasks" / "t" / "PILOT.md").write_text(PILOT + "\n## v3\n\n- Verdict: approved\n")
    assert run(root, "write") == 0
    assert lock(root)["t"]["version"] == 3
    assert run(root, "check") == 0


def test_a_version_cannot_go_down(tmp_path, capsys):
    root = repo(tmp_path, version=3)
    assert run(root, "write") == 0
    path = root / "tasks" / "t" / "task.yaml"
    data = yaml.safe_load(path.read_text())
    data["version"] = 2
    path.write_text(yaml.safe_dump(data))
    assert run(root, "check") == 1
    assert "version went down" in capsys.readouterr().err


def test_freezing_needs_an_approved_pilot(tmp_path, capsys):
    root = repo(tmp_path, pilot=False)
    assert run(root, "write") == 1
    assert "no approved review for v2" in capsys.readouterr().err
    assert not (root / "tasks" / "LOCK.json").exists(), "a refused write leaves no lock behind"


def test_freezing_needs_complete_criteria(tmp_path, capsys):
    root = repo(tmp_path)
    (root / "tasks" / "t" / "NOTES.md").write_text("# t\n")
    assert run(root, "write") == 1
    assert "lacks the section" in capsys.readouterr().err


def test_a_deleted_or_unfrozen_task_must_leave_the_lock(tmp_path, capsys):
    root = repo(tmp_path)
    assert run(root, "write") == 0
    path = root / "tasks" / "t" / "task.yaml"
    data = yaml.safe_load(path.read_text())
    data["frozen"] = False
    path.write_text(yaml.safe_dump(data))
    assert run(root, "check") == 1
    assert "frozen: false" in capsys.readouterr().err
    assert run(root, "write") == 0 and lock(root) == {}
    import shutil
    path.write_text(yaml.safe_dump({**data, "frozen": True}))
    assert run(root, "write") == 0
    shutil.rmtree(root / "tasks" / "t")
    assert run(root, "check") == 1
    assert "the task is gone" in capsys.readouterr().err


def test_the_real_repository_matches_its_lock():
    assert run(ROOT, "check") == 0
