import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = ROOT / "tasks"
SOLUTIONS_DIR = Path(__file__).resolve().parent / "solutions"
TAXONOMY = ROOT / "behaviour" / "taxonomy.yaml"
GRADELIB = Path(__file__).resolve().parent / "gradelib_block.py"


def task_ids():
    return sorted(p.name for p in TASKS_DIR.iterdir() if (p / "task.yaml").is_file())


def solution_cases():
    cases = []
    for task_id in task_ids():
        base = SOLUTIONS_DIR / task_id
        if base.is_dir():
            cases.extend((task_id, d.name) for d in sorted(base.iterdir()) if d.is_dir())
    return cases


def _scalar(text):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text in ("true", "false"):
        return text == "true"
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            pass
    return text


def parse_yaml(text):
    try:
        import yaml
    except ImportError:
        yaml = None
    if yaml is not None:
        return yaml.safe_load(text)
    lines = [l.rstrip() for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    if lines and lines[0].startswith("- "):
        items = []
        for line in lines:
            if line.startswith("- "):
                items.append({})
                line = "  " + line[2:]
            key, _, value = line.strip().partition(":")
            items[-1][key] = _scalar(value)
        return items
    data, current = {}, None
    for line in lines:
        if line.startswith("  - "):
            data[current].append(_scalar(line[4:]))
            continue
        key, _, value = line.partition(":")
        if value.strip():
            data[key] = _scalar(value)
        else:
            data[key], current = [], key
    return data


def load_task(task_id):
    return parse_yaml((TASKS_DIR / task_id / "task.yaml").read_text())


def taxonomy():
    return parse_yaml(TAXONOMY.read_text())


def clean_env(workspace):
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(workspace)})
    return env


def git_baseline(workspace):
    (workspace / "AGENTS.md").write_text("# Plumbing file added by the harness before the baseline commit\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@localhost", "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@localhost", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "baseline"]):
        subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=workspace, env=env, check=True, capture_output=True)


def make_workspace(task_id, tmp_path, solution=None, harness_like=False):
    workspace = tmp_path / "ws"
    shutil.copytree(TASKS_DIR / task_id / "fixture", workspace)
    if harness_like:
        git_baseline(workspace)
    meta = {}
    if solution:
        src = SOLUTIONS_DIR / task_id / solution
        meta_file = src / "_meta.json"
        if meta_file.exists():
            meta = json.loads(meta_file.read_text())
        for path in sorted(src.rglob("*")):
            rel = path.relative_to(src)
            if path.is_file() and rel.as_posix() != "_meta.json":
                target = workspace / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        for rel in meta.get("delete", []):
            target = workspace / rel
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
    return workspace, meta


def run_grader(task_id, workspace):
    base = Path(workspace).parent / "grader-base"
    shutil.rmtree(base, ignore_errors=True)
    shutil.copytree(TASKS_DIR / task_id / "grader", base / "grader")
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    result = subprocess.run(
        [sys.executable, "grader/run.py", str(workspace)],
        cwd=base, capture_output=True, text=True, timeout=300, env=env,
    )
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    assert len(lines) == 1, f"grader must print exactly one line, got: {result.stdout!r} {result.stderr!r}"
    return json.loads(lines[0])


def run_visible_tests(workspace):
    return subprocess.run(
        [sys.executable, "-m", "unittest"],
        cwd=workspace, capture_output=True, text=True, timeout=300, env=clean_env(workspace),
    )
