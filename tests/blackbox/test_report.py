import json

from blackbox.cli import main


def fake_run(root, run_id, task, variant, passed, cost, behaviours):
    d = root / "runs" / run_id
    d.mkdir(parents=True)
    (d / "run.json").write_text(json.dumps({
        "run_id": run_id, "task_id": task, "variant": variant, "model": "m", "agent_id": "agt-00000000",
        "agent_name": "Ember", "grade": {"passed": passed, "score": 1.0 if passed else 0.0, "checks": []},
        "cost_usd": cost, "input_tokens": 10, "output_tokens": 20, "turns": 3, "duration_ms": 5,
        "stop_reason": "success", "behaviours": [{"id": b} for b in behaviours]}))


def test_index_and_report(tmp_path):
    root = tmp_path
    fake_run(root, "20261102T000001Z-t1-bare-ember", "t1", "bare", True, 0.1, ["minimal-diff"])
    fake_run(root, "20261102T000002Z-t1-bare-quill", "t1", "bare", False, 0.3, ["premature-stop", "minimal-diff"])
    fake_run(root, "20261102T000003Z-t1-plumbed-rook", "t1", "plumbed", True, None, [])
    (root / "runs" / "broken").mkdir()
    (root / "runs" / "broken" / "run.json").write_text("{")
    assert main(["index", "--root", str(root)]) == 0
    rows = [json.loads(l) for l in (root / "runs" / "index.jsonl").read_text().splitlines()]
    assert [r["agent_name"] for r in rows] == ["Ember", "Ember", "Ember"]
    assert rows[1]["behaviours"] == ["minimal-diff", "premature-stop"]
    assert main(["report", "--root", str(root)]) == 0
    md = (root / "docs" / "results.md").read_text()
    assert "| t1 | m | bare | 2 of 2 | 1/2 (50%) | 0.50 | 0.2000 | 10 | 20 | 3.0 | minimal-diff (2), premature-stop (1) |" in md
    assert "| t1 | m | plumbed | 1 of 1 | 1/1 (100%) | 1.00 | n/a |" in md
    assert rows[0]["claim_outcome"] == "unknown" and rows[0]["confounded_by"] == []
    assert "## Confounded runs\n\nNone." in md


def test_empty_report(tmp_path):
    assert main(["report", "--root", str(tmp_path)]) == 0
    md = (tmp_path / "docs" / "results.md").read_text()
    assert "Runs: 0. Clean: 0. Confounded: 0." in md and "| none | | | 0 of 0 |" in md


def fake_model_run(root, run_id, model, passed, claim=None):
    fake_run(root, run_id, "t1", "bare", passed, 0.5, [])
    path = root / "runs" / run_id / "run.json"
    record = json.loads(path.read_text())
    record["model"] = model
    path.write_text(json.dumps(record))


def test_models_are_never_pooled(tmp_path):
    root = tmp_path
    fake_model_run(root, "20261102T000001Z-t1-bare-ember", "model-a", True)
    fake_model_run(root, "20261102T000002Z-t1-bare-quill", "model-a", True)
    fake_model_run(root, "20261102T000003Z-t1-bare-rook", "model-b", False)
    assert main(["index", "--root", str(root)]) == 0
    assert main(["report", "--root", str(root)]) == 0
    md = (root / "docs" / "results.md").read_text()
    assert "| t1 | model-a | bare | 2 of 2 | 2/2 (100%) |" in md
    assert "| t1 | model-b | bare | 1 of 1 | 0/1 (0%) |" in md
    assert "| model-a | bare | 2 | 2/2 (100%) | 0.5000 | 0 | 0 |" in md
    assert "| model-b | bare | 1 | 0/1 (0%) | 0.5000 | 0 | 0 |" in md
    assert "2/3" not in md and "(67%)" not in md


def test_by_model_counts_overclaims_and_skips_confounded_runs():
    from blackbox import report
    rows = [
        {"run_id": "a", "task_id": "t", "variant": "bare", "model": "m", "passed": False, "claim_outcome": "claimed-failed",
         "behaviours": ["claim-contradicted-by-grader"]},
        {"run_id": "b", "task_id": "t", "variant": "bare", "model": "m", "passed": True, "claim_outcome": "claimed-passed"},
        {"run_id": "d", "task_id": "t", "variant": "bare", "model": "m", "passed": False, "claim_outcome": "claimed-failed",
         "behaviours": ["verified-before-claiming"]},
        {"run_id": "c", "task_id": "t", "variant": "bare", "model": "m", "passed": False, "confounded_by": ["INC-1"]},
    ]
    md = report.render(rows, [])
    assert "| m | bare | 3 | 1/3 (33%) | n/a | 2 | 1 |" in md
    assert "| t | m | bare | 3 of 4 |" in md


def test_a_failure_of_a_rule_alone_is_not_counted_as_a_contradicted_claim():
    from blackbox import report
    rows = [{"run_id": "a", "task_id": "t", "variant": "bare", "model": "m", "passed": False, "claim_outcome": "claimed-failed",
             "behaviours": ["scope-creep"]}]
    assert "| m | bare | 1 | 0/1 (0%) | n/a | 1 | 0 |" in report.render(rows, [])


def test_a_run_with_no_model_is_labelled_unknown_not_dropped():
    from blackbox import report
    md = report.render([{"run_id": "a", "task_id": "t", "variant": "bare", "passed": True}], [])
    assert "| unknown | bare | 1 | 1/1 (100%) |" in md
    assert "| t | unknown | bare | 1 of 1 |" in md


def test_empty_by_model_table_says_none():
    from blackbox import report
    assert "| none | | 0 | | | | |" in report.render([], [])
