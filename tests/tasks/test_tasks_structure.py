import ast
import sys

import pytest

from task_helpers import GRADELIB, SOLUTIONS_DIR, TASKS_DIR, load_task, task_ids, taxonomy

REQUIRED_FIELDS = {"id", "title", "difficulty", "traps", "timeout_seconds", "max_budget_usd", "max_turns"}


def test_there_are_at_least_eight_tasks():
    assert len(task_ids()) >= 8


@pytest.mark.parametrize("task_id", task_ids())
def test_task_files_present(task_id):
    task = TASKS_DIR / task_id
    for name in ("task.yaml", "PROMPT.md", "NOTES.md", "grader/run.py"):
        assert (task / name).is_file(), name
    assert (task / "fixture").is_dir()
    assert any((task / "fixture").rglob("test*.py")), "fixture needs visible unittest tests"


@pytest.mark.parametrize("task_id", task_ids())
def test_task_yaml_valid(task_id):
    data = load_task(task_id)
    assert REQUIRED_FIELDS <= set(data)
    assert data["id"] == task_id
    assert data["difficulty"] in ("medium", "hard")
    assert isinstance(data["title"], str) and data["title"]
    known = {e["id"]: e["kind"] for e in taxonomy()}
    assert data["traps"], "every task needs at least one trap"
    for trap in data["traps"]:
        assert known.get(trap) == "bad", trap
    for good in data.get("good_behaviours", []):
        assert known.get(good) == "good", good
    assert 0 < data["timeout_seconds"] <= 3600
    assert 0 < data["max_budget_usd"] <= 5
    assert 15 <= data["max_turns"] <= 80
    assert isinstance(data.get("scope", []), list)
    assert all(isinstance(m, str) and m for m in data.get("injection_markers", []))
    if "expected_diff_lines" in data:
        assert isinstance(data["expected_diff_lines"], int) and data["expected_diff_lines"] > 0
    assert 10 <= data["expected_turns_min"] <= data["expected_turns_max"] <= 40


@pytest.mark.parametrize("task_id", task_ids())
def test_prompt_requires_a_summary(task_id):
    prompt = (TASKS_DIR / task_id / "PROMPT.md").read_text()
    assert "SUMMARY.md" in prompt
    assert "did not verify" in prompt


@pytest.mark.parametrize("task_id", task_ids())
def test_notes_cover_the_trap(task_id):
    notes = (TASKS_DIR / task_id / "NOTES.md").read_text()
    for heading in ("## What is tested", "## The trap", "## Good behaviour", "## Grader", "## Expected length"):
        assert heading in notes, heading


@pytest.mark.parametrize("task_id", task_ids())
def test_grader_uses_only_the_standard_library(task_id):
    source = (TASKS_DIR / task_id / "grader" / "run.py").read_text()
    for node in ast.walk(ast.parse(source)):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names = [node.module]
        for name in names:
            assert name.split(".")[0] in sys.stdlib_module_names, name


@pytest.mark.parametrize("task_id", task_ids())
def test_grader_embeds_the_shared_helpers_verbatim(task_id):
    source = (TASKS_DIR / task_id / "grader" / "run.py").read_text()
    assert source.startswith(GRADELIB.read_text())


@pytest.mark.parametrize("task_id", task_ids())
def test_solutions_exist_and_stay_outside_the_task(task_id):
    base = SOLUTIONS_DIR / task_id
    names = [d.name for d in base.iterdir() if d.is_dir()]
    assert any(n.startswith("good") for n in names)
    assert any(n.startswith("cheat") for n in names)
    assert not list((TASKS_DIR / task_id).rglob("solution*"))


def test_grader_baselines_match_fixtures():
    import build_baselines

    assert build_baselines.main(check=True) == []
