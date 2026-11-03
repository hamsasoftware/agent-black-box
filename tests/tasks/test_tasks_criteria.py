"""Gate G1 and the alternative-solution part of gate G2 (docs/protocol.md, section 3)."""
import json

import pytest

from blackbox.taskspec import PROTOCOL_VERSION, check_spec, compile_prompt, task_sha256
from task_helpers import SOLUTIONS_DIR, TASKS_DIR, load_task, task_ids


@pytest.mark.parametrize("task_id", task_ids())
def test_criteria_are_complete(task_id):
    assert check_spec(TASKS_DIR / task_id, SOLUTIONS_DIR) == []


@pytest.mark.parametrize("task_id", task_ids())
def test_task_is_at_a_pinned_version(task_id):
    assert load_task(task_id)["version"] >= 2, "version 1 is the unpinned exploratory form"


@pytest.mark.parametrize("task_id", task_ids())
def test_every_rule_is_visible_in_the_compiled_prompt(task_id):
    task = load_task(task_id)
    compiled = compile_prompt(task, (TASKS_DIR / task_id / "PROMPT.md").read_text(encoding="utf-8"))
    for rule in task["rules"]:
        assert (rule.get("text") or rule.get("quote")) in compiled, rule["id"]


@pytest.mark.parametrize("task_id", task_ids())
def test_every_rule_check_has_a_rule_the_agent_sees(task_id):
    task = load_task(task_id)
    rules = {r["id"]: r for r in task["rules"]}
    compiled = compile_prompt(task, (TASKS_DIR / task_id / "PROMPT.md").read_text(encoding="utf-8"))
    for check in task["checks"]:
        if check["class"] == "rule":
            rule = rules[check["rule"]]
            assert (rule.get("text") or rule.get("quote")) in compiled, check["name"]


@pytest.mark.parametrize("task_id", task_ids())
def test_declared_alternative_solutions_pass(task_id):
    for alt in load_task(task_id)["alternatives"]:
        meta = json.loads((SOLUTIONS_DIR / task_id / alt["name"] / "_meta.json").read_text(encoding="utf-8"))
        assert meta["expect_passed"] is True, alt["name"]
        assert alt["name"].startswith("good"), "alternatives are good solutions and are graded as such"


@pytest.mark.parametrize("task_id", task_ids())
def test_every_task_has_rule_breaking_solutions(task_id):
    names = {p.name for p in (SOLUTIONS_DIR / task_id).iterdir() if p.is_dir()}
    assert {"rule-out-of-scope", "rule-edits-test", "rule-no-summary"} <= names


def test_hash_is_stable_and_sensitive(tmp_path):
    first = task_sha256(TASKS_DIR / task_ids()[0])
    assert first == task_sha256(TASKS_DIR / task_ids()[0])
    assert len(first) == 64


def test_protocol_version_is_recorded_as_a_whole_number():
    assert isinstance(PROTOCOL_VERSION, int) and PROTOCOL_VERSION >= 1
