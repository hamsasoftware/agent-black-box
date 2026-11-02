import json
import os
import shutil
from pathlib import Path

import pytest

from blackbox.runner import RunOptions, run

FIXTURES = Path(__file__).parent / "fixtures"
FAKE_KEY = "sk-ant-" + "api03-" + "Zq7" * 12
OTHER_SECRET = "hunter2-" + "w" * 12


@pytest.fixture
def env_file(tmp_path):
    path = tmp_path / "secrets.env"
    path.write_text(f"# test\nexport ANTHROPIC_API_KEY=\"{FAKE_KEY}\"\nOTHER={OTHER_SECRET}\nSHORT=1\n")
    return path


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "repo"
    (r / "behaviour").mkdir(parents=True)
    shutil.copy(FIXTURES / "taxonomy.yaml", r / "behaviour" / "taxonomy.yaml")
    return r


@pytest.fixture
def task_dir(tmp_path):
    dst = tmp_path / "task-demo"
    shutil.copytree(FIXTURES / "task-demo", dst)
    return dst


@pytest.fixture
def do_run(root, task_dir, env_file, tmp_path, monkeypatch):
    def go(scenario, variant="bare", sandbox="off", extra_env=None, **kw):
        monkeypatch.setenv("BLACKBOX_CANARY", "leaky")
        env = {"FAKE_AGENT_SCENARIO": scenario, "FAKE_OUTSIDE_PATH": str(task_dir / "PROMPT.md"), **(extra_env or {})}
        opts = RunOptions(task_dir=task_dir, variant=variant, model="claude-sonnet-5-5", budget_usd=0.75,
                          root=root, env_file=str(env_file), agent_cli=str(FIXTURES / "fake_agent.py"),
                          sandbox=sandbox, extra_env=env, **kw)
        run_dir = run(opts)
        record = json.loads((run_dir / "run.json").read_text())
        events = [json.loads(l)["event"] for l in (run_dir / "events.jsonl").read_text().splitlines()]
        probe = next((e for e in events if e.get("type") == "fake_probe"), None)
        return run_dir, record, probe
    return go


def sandbox_works():
    from blackbox import sandbox
    return sandbox.probe()[0]


@pytest.fixture
def needs_sandbox():
    if not sandbox_works():
        pytest.skip("bwrap sandbox unavailable here")


def all_text(path: Path) -> str:
    return "\n".join(p.read_text() for p in sorted(path.rglob("*")) if p.is_file())
