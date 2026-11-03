import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from blackbox.cli import parser

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")


def make(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["make", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=60)


def task_id() -> str:
    return sorted(path.name for path in (ROOT / "tasks").iterdir() if path.is_dir())[0]


def command_of(result: subprocess.CompletedProcess) -> list[str]:
    line = next(line for line in result.stdout.splitlines() if "-m blackbox run" in line and not line.startswith("if"))
    words = shlex.split(line)
    return words[words.index("run"):]


def test_run_task_builds_a_command_the_harness_accepts():
    result = make("-n", "run-task", f"TASK={task_id()}", "VARIANT=plumbed", "MODEL=some-model")
    assert result.returncode == 0
    args = parser().parse_args(command_of(result))
    assert args.task == task_id() and args.variant == "plumbed" and args.model == "some-model"
    assert args.budget_usd is None


def test_budget_is_passed_through_when_given():
    result = make("-n", "run-task", f"TASK={task_id()}", "VARIANT=bare", "MODEL=m", "BUDGET=0.4")
    args = parser().parse_args(command_of(result))
    assert args.budget_usd == 0.4


def test_a_missing_model_stops_before_anything_is_spent():
    result = make("run-task", f"TASK={task_id()}", "VARIANT=bare")
    assert result.returncode == 2
    assert "Set MODEL=" in result.stdout + result.stderr
    assert "runs/" not in result.stdout


@pytest.mark.parametrize("arguments, message", [
    (["VARIANT=bare", "MODEL=m"], "Set TASK="),
    (["TASK=does-not-exist", "VARIANT=bare", "MODEL=m"], "No such task"),
])
def test_other_missing_inputs_are_refused(arguments, message):
    result = make("run-task", *arguments)
    assert result.returncode == 2 and message in result.stdout + result.stderr


def test_a_bad_variant_is_refused():
    result = make("run-task", f"TASK={task_id()}", "VARIANT=other", "MODEL=m")
    assert result.returncode == 2 and "VARIANT must be" in result.stdout + result.stderr


def test_help_documents_the_model_variable():
    result = make("help")
    assert "MODEL=<model-id>" in result.stdout
