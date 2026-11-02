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
    assert "| t1 | bare | 2 of 2 | 1/2 (50%) | 0.50 | 0.2000 | 10 | 20 | 3.0 | minimal-diff (2), premature-stop (1) |" in md
    assert "| t1 | plumbed | 1 of 1 | 1/1 (100%) | 1.00 | n/a |" in md
    assert rows[0]["claim_outcome"] == "unknown" and rows[0]["confounded_by"] == []
    assert "## Confounded runs\n\nNone." in md


def test_empty_report(tmp_path):
    assert main(["report", "--root", str(tmp_path)]) == 0
    md = (tmp_path / "docs" / "results.md").read_text()
    assert "Runs: 0. Clean: 0. Confounded: 0." in md and "| none | | 0 of 0 |" in md
