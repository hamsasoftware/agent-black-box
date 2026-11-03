import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("update_readme_facts", ROOT / "scripts" / "update_readme_facts.py")
readme_facts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(readme_facts)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def run(variant: str, passed: bool, **extra) -> dict:
    return {"variant": variant, "passed": passed, "cost_usd": 0.25, **extra}


@pytest.fixture()
def tree(tmp_path: Path) -> Path:
    write_jsonl(tmp_path / "runs" / "index.jsonl", [
        run("bare", True),
        run("bare", False, claim_outcome="claimed-failed"),
        run("plumbed", True),
        run("plumbed", False, confounded_by=["guard-bug"]),
    ])
    write_jsonl(tmp_path / "ledger" / "agents.jsonl", [
        {"kind": "builder"}, {"kind": "builder"}, {"kind": "subject"},
    ])
    write_jsonl(tmp_path / "ledger" / "incidents.jsonl", [{"status": "open"}, {"status": "fixed"}, {"status": "open"}])
    (tmp_path / "behaviour").mkdir()
    (tmp_path / "behaviour" / "taxonomy.yaml").write_text("- id: a\n- id: b\n  note: x\n- id: c\n", encoding="utf-8")
    for task in ("one", "two"):
        (tmp_path / "tasks" / task).mkdir(parents=True)
        (tmp_path / "tasks" / task / "task.yaml").write_text("id: x\n", encoding="utf-8")
    return tmp_path


def readme_with_block(text: str = "old") -> str:
    return f"# Title\n\nintro\n\n{readme_facts.START}\n{text}\n{readme_facts.END}\n\nafter\n"


def test_facts_count_everything_from_the_data(tree):
    values = readme_facts.facts(tree)
    assert values == {
        "tasks": 2, "runs": 4, "clean": 3, "confounded": 1,
        "bare": (1, 2), "plumbed": (1, 1), "claimed_failed": 1, "cost": 1.0,
        "builders": 2, "subjects": 1, "behaviours": 3, "incidents": 3, "open": 2,
    }


def test_facts_on_an_empty_tree_are_zero(tmp_path):
    values = readme_facts.facts(tmp_path)
    assert values["runs"] == 0 and values["tasks"] == 0 and values["behaviours"] == 0
    assert values["bare"] == (0, 0) and values["cost"] == 0


def test_block_is_a_markdown_table_with_every_fact(tree):
    text = readme_facts.block(readme_facts.facts(tree))
    lines = text.splitlines()
    assert lines[0] == "| At a glance | Now |" and lines[1] == "|---|---|"
    assert "| Challenging tasks | 2, each with a hidden grader |" in lines
    assert "| Recorded runs | 4: 3 clean, 1 set aside as confounded |" in lines
    assert "| Clean runs that passed | bare 1 of 2, plumbed 1 of 1 |" in lines
    assert "| Cost of every run | $1.00 |" in lines
    assert "| Errors logged | 3, 2 still open |" in lines
    assert len(lines) == 10


def test_rendered_replaces_only_the_block_and_is_idempotent(tree):
    values = readme_facts.facts(tree)
    once = readme_facts.rendered(readme_with_block(), values)
    assert once.startswith("# Title\n\nintro\n\n") and once.endswith("\n\nafter\n")
    assert "| Challenging tasks |" in once and "old" not in once
    assert readme_facts.rendered(once, values) == once


def test_rendered_needs_both_markers():
    for text in ("no markers", f"{readme_facts.START} only start", f"only end {readme_facts.END}"):
        with pytest.raises(ValueError, match="markers"):
            readme_facts.rendered(text, {})


def test_write_then_check_round_trip(tree, capsys):
    (tree / "README.md").write_text(readme_with_block(), encoding="utf-8")
    assert readme_facts.main(["check", "--root", str(tree)]) == 1
    assert "out of date" in capsys.readouterr().err
    assert readme_facts.main(["write", "--root", str(tree)]) == 0
    assert readme_facts.main(["check", "--root", str(tree)]) == 0
    assert "match the data" in capsys.readouterr().out


def test_check_fails_again_when_the_data_moves(tree):
    (tree / "README.md").write_text(readme_with_block(), encoding="utf-8")
    assert readme_facts.main(["write", "--root", str(tree)]) == 0
    write_jsonl(tree / "ledger" / "incidents.jsonl", [{"status": "open"}])
    assert readme_facts.main(["check", "--root", str(tree)]) == 1


def test_missing_readme_or_markers_is_an_error_not_a_crash(tree, capsys):
    assert readme_facts.main(["check", "--root", str(tree)]) == 1
    (tree / "README.md").write_text("no markers here", encoding="utf-8")
    assert readme_facts.main(["write", "--root", str(tree)]) == 1
    assert "readme-facts:" in capsys.readouterr().err


def test_the_real_readme_is_current():
    assert readme_facts.main(["check"]) == 0
