import copy
from pathlib import Path

import pytest
import yaml

from blackbox import taskspec

GRADER = '''
class G:
    def add(self, *a, **k):
        pass

g = G()
g.add("only-allowed-files-changed", True, "ok")
g.add("works", True, "ok")
g.add("hidden-behaviour", True, "ok")
g.add("nice-to-have", True, "ok", required=False)
g.add("grader-error", False, "crash")
'''

TASK = {
    "id": "t", "version": 2, "frozen": False, "scope": ["src/*", "SUMMARY.md"],
    "rules": [
        {"id": "scope", "text": "Change only these files: files under `src/`, and `SUMMARY.md`."},
        {"id": "summary", "quote": "write a summary"},
    ],
    "checks": [
        {"name": "only-allowed-files-changed", "class": "rule", "rule": "scope", "why": "scope"},
        {"name": "works", "class": "result", "why": "the prompt asks for it"},
        {"name": "hidden-behaviour", "class": "trap", "why": "a careful engineer does it"},
        {"name": "nice-to-have", "class": "advisory", "why": "informative"},
    ],
    "alternatives": [{"name": "good-alt", "why": "another way"}],
}
NOTES = """# t

## Criteria

x

## Hidden by design

- `hidden-behaviour`: because

## Version history

- v2 (2026-11-03): pinned.
"""


def make(tmp_path: Path, task=None, notes=NOTES, grader=GRADER, prompt="Please write a summary to SUMMARY.md.") -> Path:
    root = tmp_path / "t"
    (root / "grader").mkdir(parents=True, exist_ok=True)
    (root / "fixture").mkdir(exist_ok=True)
    (root / "fixture" / "a.txt").write_text("a")
    (root / "grader" / "run.py").write_text(grader)
    (root / "task.yaml").write_text(yaml.safe_dump(task or TASK))
    (root / "PROMPT.md").write_text(prompt)
    (root / "NOTES.md").write_text(notes)
    solutions = tmp_path / "solutions" / "t" / "good-alt"
    solutions.mkdir(parents=True, exist_ok=True)
    return root


def problems(tmp_path, **kwargs):
    root = make(tmp_path, **kwargs)
    return taskspec.check_spec(root, tmp_path / "solutions")


def changed(**edits):
    task = copy.deepcopy(TASK)
    task.update(edits)
    return task


def test_a_complete_spec_has_no_problems(tmp_path):
    assert problems(tmp_path) == []


def test_a_rule_quote_missing_from_the_prompt_is_reported(tmp_path):
    assert any("not in PROMPT.md" in p for p in problems(tmp_path, prompt="Do the work."))


def test_a_rule_needs_exactly_one_of_text_or_quote(tmp_path):
    task = changed(rules=[{"id": "scope", "text": "Change only files under `src/` and `SUMMARY.md`.", "quote": "x"}, {"id": "summary", "quote": "write a summary"}])
    assert any("exactly one of text or quote" in p for p in problems(tmp_path, task=task))


def test_the_scope_rule_must_mention_every_scope_entry(tmp_path):
    task = changed(rules=[{"id": "scope", "text": "Change only files under `src/`."}, {"id": "summary", "quote": "write a summary"}])
    assert any("does not mention SUMMARY.md" in p for p in problems(tmp_path, task=task))


def test_a_scope_without_a_scope_rule_is_reported(tmp_path):
    task = changed(rules=[{"id": "summary", "quote": "write a summary"}])
    out = problems(tmp_path, task=task)
    assert any("needs a rule with id scope" in p for p in out)
    assert any("must name a declared rule" in p for p in out)


def test_an_undeclared_grader_check_is_reported(tmp_path):
    task = changed(checks=TASK["checks"][:3])
    assert any("nice-to-have, which is not declared" in p for p in problems(tmp_path, task=task))


def test_a_declared_check_the_grader_never_emits_is_reported_unless_conditional(tmp_path):
    ghost = {"name": "ghost", "class": "result", "why": "nothing emits this"}
    task = changed(checks=TASK["checks"] + [ghost])
    assert any("ghost is declared but the grader never emits it" in p for p in problems(tmp_path, task=task))
    ghost["conditional"] = True
    assert problems(tmp_path, task=changed(checks=TASK["checks"] + [ghost])) == []


def test_advisory_must_match_the_graders_required_flag(tmp_path):
    flipped = copy.deepcopy(TASK["checks"])
    flipped[3]["class"] = "result"
    flipped[1]["class"] = "advisory"
    out = problems(tmp_path, task=changed(checks=flipped))
    assert any("nice-to-have is advisory in the grader but not declared advisory" in p for p in out)
    assert any("works is declared advisory but the grader requires it" in p for p in out)


def test_every_check_needs_a_class_and_a_why(tmp_path):
    bad = copy.deepcopy(TASK["checks"])
    bad[1]["class"] = "mystery"
    bad[2]["why"] = " "
    out = problems(tmp_path, task=changed(checks=bad))
    assert any("works needs a class" in p for p in out)
    assert any("hidden-behaviour needs a why" in p for p in out)


def test_a_trap_must_be_listed_under_hidden_by_design(tmp_path):
    notes = NOTES.replace("`hidden-behaviour`", "`something-else`")
    assert any("trap check hidden-behaviour is not listed" in p for p in problems(tmp_path, notes=notes))


def test_notes_need_the_sections_and_a_version_entry(tmp_path):
    out = problems(tmp_path, notes="# t\n")
    assert any("lacks the section ## Criteria" in p for p in out)
    assert any("no entry for v2" in p for p in problems(tmp_path, notes=NOTES.replace("v2", "v1")))


def test_alternatives_must_exist_and_be_explained(tmp_path):
    root = make(tmp_path)
    (tmp_path / "solutions" / "t" / "good-alt").rmdir()
    assert any("has no solution directory" in p for p in taskspec.check_spec(root, tmp_path / "solutions"))
    assert any("at least one alternative" in p for p in problems(tmp_path / "again", task=changed(alternatives=[])))


def test_a_bad_version_is_reported(tmp_path):
    assert any("version must be" in p for p in problems(tmp_path, task=changed(version="two")))


def test_compile_prompt_appends_only_text_rules():
    compiled = taskspec.compile_prompt(TASK, "Please write a summary.\n")
    assert compiled.startswith("Please write a summary.\n\nRules for this task:\n- Change only these files")
    assert "write a summary\n" not in compiled.split("Rules for this task:")[1]
    assert taskspec.compile_prompt({}, "unchanged\n") == "unchanged\n"


def test_hash_changes_with_any_defining_file(tmp_path):
    root = make(tmp_path)
    before = taskspec.task_sha256(root)
    (root / "grader" / "run.py").write_text(GRADER + "\n# edit\n")
    assert taskspec.task_sha256(root) != before
    after = taskspec.task_sha256(root)
    (root / "fixture" / "pycache_ignored.pyc").write_bytes(b"x")
    (root / "fixture" / "__pycache__").mkdir()
    (root / "fixture" / "__pycache__" / "x.py").write_text("ignored")
    assert taskspec.task_sha256(root) == after
    (root / "fixture" / "a.txt").write_text("changed")
    assert taskspec.task_sha256(root) != after


def test_grader_checks_reads_names_and_the_advisory_flag(tmp_path):
    root = make(tmp_path)
    names, advisory = taskspec.grader_checks(root / "grader" / "run.py")
    assert names == {"only-allowed-files-changed", "works", "hidden-behaviour", "nice-to-have", "grader-error"}
    assert advisory == {"nice-to-have"}


def test_the_graders_own_crash_marker_is_not_a_criterion(tmp_path):
    assert problems(tmp_path) == []


def test_frozen_must_be_true_or_false(tmp_path):
    assert any("frozen must be true or false" in p for p in problems(tmp_path, task=changed(frozen="yes")))


def test_pilot_approval_needs_a_section_for_the_version_with_an_approved_verdict(tmp_path):
    root = make(tmp_path)
    assert taskspec.pilot_approved(root, 2) is False
    (root / "PILOT.md").write_text("# Pilot\n\n## v2\n\n- Verdict: rejected\n")
    assert taskspec.pilot_approved(root, 2) is False
    (root / "PILOT.md").write_text("# Pilot\n\n## v1\n\n- Verdict: approved\n")
    assert taskspec.pilot_approved(root, 2) is False, "approval of another version does not count"
    (root / "PILOT.md").write_text("# Pilot\n\n## v1\n\n- Verdict: rejected\n\n## v2\n\n- Runs: a, b\n- Verdict: approved\n")
    assert taskspec.pilot_approved(root, 2) is True
