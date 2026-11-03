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


def run(variant: str, passed: bool, model: str = "model-a", **extra) -> dict:
    return {"variant": variant, "passed": passed, "model": model, "cost_usd": 0.25, **extra}


@pytest.fixture()
def tree(tmp_path: Path) -> Path:
    write_jsonl(tmp_path / "runs" / "index.jsonl", [
        run("bare", True),
        run("bare", False, claim_outcome="claimed-failed", behaviours=["claim-contradicted-by-grader"]),
        run("plumbed", True),
        run("plumbed", False, confounded_by=["guard-bug"]),
        run("bare", True, model="model-b"),
        run("bare", False, model="model-b", claim_outcome="claimed-failed"),
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


BOTH = {"claim-classifier": "passed", "claim-contradicted-by-grader": "passed"}


def readme_with_block(text: str = "old") -> str:
    return f"# Title\n\nintro\n\n{readme_facts.START}\n{text}\n{readme_facts.END}\n\nafter\n"


def test_facts_count_everything_from_the_data(tree):
    values = readme_facts.facts(tree, BOTH)
    assert values == {
        "tasks": 2, "runs": 6, "clean": 5, "confounded": 1,
        "models": {
            "model-a, exploratory": {"clean": 3, "claimed_failed": 1, "contradicted": 1, "bare": (1, 2), "plumbed": (1, 1)},
            "model-b, exploratory": {"clean": 2, "claimed_failed": 1, "contradicted": 0, "bare": (1, 2), "plumbed": (0, 0)},
        },
        "cost": 1.5, "builders": 2, "subjects": 1, "behaviours": 3, "incidents": 3, "open": 2,
    }


def test_facts_on_an_empty_tree_are_zero(tmp_path):
    values = readme_facts.facts(tmp_path)
    assert values["runs"] == 0 and values["tasks"] == 0 and values["behaviours"] == 0
    assert values["models"] == {} and values["cost"] == 0


def test_block_is_a_markdown_table_with_every_fact(tree):
    text = readme_facts.block(readme_facts.facts(tree, BOTH))
    lines = text.splitlines()
    assert lines[0] == "| At a glance | Now |" and lines[1] == "|---|---|"
    assert "| Challenging tasks | 2, each with a hidden grader |" in lines
    assert "| Recorded runs | 6: 5 clean, 1 set aside as confounded |" in lines
    assert "| Clean runs passed, model-a, exploratory | bare 1 of 2, plumbed 1 of 1; 1 of 3 claimed success and failed the hidden grader (1 contradicted by a result check) |" in lines
    assert "| Clean runs passed, model-b, exploratory | bare 1 of 2; 1 of 2 claimed success and failed the hidden grader (0 contradicted by a result check) |" in lines
    assert "| Cost of every run | $1.50 |" in lines
    assert "| Errors logged | 3, 2 still open |" in lines
    assert len(lines) == 10


def test_models_are_listed_separately_never_pooled(tree):
    text = readme_facts.block(readme_facts.facts(tree))
    assert "bare 2 of 4" not in text and "bare 2 of 3" not in text
    assert text.count("Clean runs passed,") == 2


def test_a_run_without_a_model_is_counted_as_unknown(tmp_path):
    write_jsonl(tmp_path / "runs" / "index.jsonl", [{"variant": "bare", "passed": True}])
    assert list(readme_facts.facts(tmp_path)["models"]) == ["unknown, exploratory"]


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


def test_protocol_runs_are_counted_apart_from_exploratory_runs(tmp_path):
    write_jsonl(tmp_path / "runs" / "index.jsonl", [
        run("bare", True),
        run("bare", False, protocol_version=1, task_version=2),
        run("bare", True, protocol_version=1, task_version=2),
    ])
    models = readme_facts.facts(tmp_path)["models"]
    assert models["model-a, exploratory"]["bare"] == (1, 1)
    assert models["model-a, protocol 1"]["bare"] == (1, 2)
    text = readme_facts.block(readme_facts.facts(tmp_path))
    assert "Clean runs passed, model-a, protocol 1 | bare 1 of 2" in text


def test_unaudited_classifier_prints_no_claim_counts(tree):
    for states in ({}, {"claim-classifier": "failed", "claim-contradicted-by-grader": "passed"}):
        values = readme_facts.facts(tree, states)
        assert values["models"]["model-a, exploratory"]["claimed_failed"] is None
        assert values["models"]["model-a, exploratory"]["contradicted"] is None
        text = readme_facts.block(values)
        assert "| Clean runs passed, model-a, exploratory | bare 1 of 2, plumbed 1 of 1; claim figures unaudited |" in text
        assert "claimed success" not in text and "contradicted" not in text
        assert "bare 1 of 2" in text  # the grader pass rate is still shown


def test_contradicted_is_unaudited_until_its_own_tag_passes(tree):
    text = readme_facts.block(readme_facts.facts(tree, {"claim-classifier": "passed"}))
    assert ("| Clean runs passed, model-a, exploratory | bare 1 of 2, plumbed 1 of 1; 1 of 3 claimed success and failed "
            "the hidden grader (contradicted by a result check: unaudited) |") in text


def test_facts_read_the_audit_ledger_when_no_states_are_given(tree):
    values = readme_facts.facts(tree)
    assert values["models"]["model-a, exploratory"]["claimed_failed"] is None


def test_the_real_readme_facts_are_gated_on_the_real_audit_ledger():
    values = readme_facts.facts()
    states = readme_facts.audit_states()
    if states.get("claim-classifier") != "passed":
        assert all(m["claimed_failed"] is None for m in values["models"].values())
        assert "claimed success" not in readme_facts.block(values)
