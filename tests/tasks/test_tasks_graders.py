from collections import defaultdict

import pytest

from task_helpers import load_task, make_workspace, run_grader, run_visible_tests, solution_cases, task_ids


# Check names failed by the untouched fixture or by a non-reference solution, per task (gate G2: every required check can fail).
FAILED_BY = defaultdict(set)


def check_shape(grade):
    assert set(grade) == {"passed", "score", "checks"}
    assert isinstance(grade["passed"], bool)
    assert 0 <= grade["score"] <= 1
    assert grade["checks"]
    for check in grade["checks"]:
        assert set(check) == {"name", "passed", "detail"}


@pytest.mark.parametrize("task_id", task_ids())
def test_untouched_fixture_fails_visible_tests_and_grader(task_id, tmp_path):
    workspace, _ = make_workspace(task_id, tmp_path)
    if load_task(task_id).get("fixture_tests") != "flaky":
        result = run_visible_tests(workspace)
        assert result.returncode != 0, result.stderr[-2000:]
    grade = run_grader(task_id, workspace)
    check_shape(grade)
    assert grade["passed"] is False
    FAILED_BY[task_id].update(c["name"] for c in grade["checks"] if not c["passed"])


@pytest.mark.parametrize("task_id,solution", solution_cases())
def test_reference_and_cheating_solutions(task_id, solution, tmp_path):
    workspace, meta = make_workspace(task_id, tmp_path, solution, harness_like=solution.startswith("good"))
    grade = run_grader(task_id, workspace)
    check_shape(grade)
    failed = {c["name"] for c in grade["checks"] if not c["passed"]}
    if not solution.startswith("good"):
        FAILED_BY[task_id].update(failed)
    assert grade["passed"] is meta["expect_passed"], grade
    for name in meta.get("expect_failed", []):
        assert name in failed, (name, grade)
    if meta["expect_passed"]:
        scope = load_task(task_id).get("scope")
        if scope:
            from fnmatch import fnmatch

            from task_helpers import SOLUTIONS_DIR

            overlay = SOLUTIONS_DIR / task_id / solution
            for path in overlay.rglob("*"):
                rel = path.relative_to(overlay).as_posix()
                if path.is_file() and rel != "_meta.json":
                    assert any(fnmatch(rel, g) for g in scope), rel
        assert not failed - set(meta.get("allow_failed", [])), grade
        expected = meta.get("visible_tests", "pass")
        if expected != "any":
            result = run_visible_tests(workspace)
            assert (result.returncode == 0) is (expected == "pass"), result.stderr[-2000:]


FLAKY_PROBE = """
import unittest
loader = unittest.defaultTestLoader
failures = 0
for _ in range(400):
    suite = loader.discover("tests", top_level_dir=".")
    result = unittest.TestResult()
    suite.run(result)
    failures += bool(result.failures or result.errors)
print(failures)
"""


@pytest.mark.parametrize("task_id", [t for t in task_ids() if load_task(t).get("fixture_tests") == "flaky"])
def test_flaky_fixture_fails_sometimes_but_not_always(task_id, tmp_path):
    import subprocess
    import sys

    from task_helpers import clean_env

    workspace, _ = make_workspace(task_id, tmp_path)
    result = subprocess.run([sys.executable, "-c", FLAKY_PROBE], cwd=workspace, capture_output=True, text=True, env=clean_env(workspace), timeout=300)
    failures = int(result.stdout.strip())
    assert 20 < failures < 380, failures


@pytest.mark.parametrize("task_id", task_ids())
def test_every_required_check_can_fail(task_id):
    """Gate G2: each required check is failed by the untouched fixture or by at least one cheating solution."""
    if task_id not in FAILED_BY:
        pytest.skip("graders were not run in this session")
    declared = load_task(task_id)["checks"]
    required = [c["name"] for c in declared if c["class"] != "advisory" and not c.get("conditional")]
    never = [name for name in required if name not in FAILED_BY[task_id]]
    assert never == [], f"no reference solution fails these required checks, so they are untested: {never}"
