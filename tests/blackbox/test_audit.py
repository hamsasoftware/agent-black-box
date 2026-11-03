import importlib.util
import json
import re
from pathlib import Path

import pytest

from blackbox import audit, behaviours, report
from blackbox.cli import main

TAG = "scope-creep"
OTHER = "thrashing"
ROOT_REPO = Path(__file__).resolve().parents[2]


def run_id(n, task="t1", variant="bare"):
    return f"20261102T{n:06d}Z-{task}-{variant}-ember"


def row(n, tags=(), task="t1", model="m", variant="bare", **extra):
    return {"run_id": run_id(n, task, variant), "task_id": task, "model": model, "variant": variant, "passed": True,
            "behaviours": sorted(tags), "claim_outcome": "claimed-passed", "confounded_by": [], **extra}


def write_index(root, rows):
    (root / "runs").mkdir(parents=True, exist_ok=True)
    (root / "runs" / "index.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def world(n_tagged=12, n_untagged=14):
    """n_tagged tagged runs and n_untagged untagged runs in the same cell, plus untagged runs in a cell with no tag."""
    rows = [row(i, [TAG]) for i in range(1, n_tagged + 1)]
    rows += [row(100 + i) for i in range(n_untagged)]
    rows += [row(200 + i, task="t2") for i in range(5)]
    return rows


@pytest.fixture
def root(tmp_path):
    write_index(tmp_path, world())
    return tmp_path


def record_all(root, tag=TAG, seed=1, tagged=None, untagged=None, default="correct"):
    """Record the whole sample, with per-run-id verdict overrides."""
    picked = audit.sample(audit.load_index(root), tag, seed)
    for group, rows in picked.items():
        for r in rows:
            verdict = ((tagged if group == "tagged" else untagged) or {}).get(r["run_id"], default)
            audit.record(root, tag=tag, group=group, seed=seed, run_id=r["run_id"], verdict=verdict,
                         reviewer="Rev", on="2026-11-03", note="checked events and diff")
    return picked


def state(root, tag=TAG):
    return audit.statuses(root)[tag]


# ---------------------------------------------------------------- sampling

def test_sampling_is_deterministic_and_seed_dependent(root):
    rows = audit.load_index(root)
    a = audit.sample(rows, TAG, 7)
    assert a == audit.sample(list(reversed(rows)), TAG, 7)
    assert [r["run_id"] for r in a["tagged"]] != [r["run_id"] for r in audit.sample(rows, TAG, 8)["tagged"]]
    assert len(a["tagged"]) == 10 and len(a["untagged"]) == 10


def test_tagged_and_untagged_selection(root):
    rows = audit.load_index(root)
    rows.append(row(300, [TAG], task="t3", variant="plumbed", confounded_by=["INC-1"]))
    picked = audit.sample(rows, TAG, 3)
    assert all(TAG in r["behaviours"] for r in picked["tagged"])
    assert all(TAG not in r["behaviours"] and r["task_id"] == "t1" for r in picked["untagged"])
    assert run_id(300, "t3", "plumbed") not in {r["run_id"] for g in picked.values() for r in g}


def test_ten_or_fewer_tagged_runs_are_all_reviewed():
    rows = [row(i, [TAG]) for i in range(1, 5)] + [row(50 + i) for i in range(3)]
    picked = audit.sample(rows, TAG, 99)
    assert len(picked["tagged"]) == 4 and len(picked["untagged"]) == 3


def test_a_tag_that_never_occurs_has_nothing_to_sample():
    assert audit.sample([row(1)], TAG, 1) == {"tagged": [], "untagged": []}


# ---------------------------------------------------------------- fingerprint

def test_fingerprint_is_stable_and_per_tag(root):
    assert audit.fingerprint(TAG, root) == audit.fingerprint(TAG, root)
    assert audit.fingerprint(TAG, root) != audit.fingerprint(OTHER, root)
    assert re.fullmatch(r"[0-9a-f]{64}", audit.fingerprint(audit.CLASSIFIER, root))


def test_editing_a_detector_changes_its_fingerprint_only(root, monkeypatch):
    before, other = audit.fingerprint(TAG, root), audit.fingerprint(OTHER, root)
    old = behaviours.REGISTRY[TAG]

    def edited(c):
        return [behaviours.ev(None, "always")]
    monkeypatch.setitem(behaviours.REGISTRY, TAG, behaviours.Detector(TAG, old.confidence, edited, old.needs))
    assert audit.fingerprint(TAG, root) != before
    assert audit.fingerprint(OTHER, root) == other


def test_editing_a_pattern_or_helper_the_detector_reads_changes_the_fingerprint(root, monkeypatch):
    before = audit.fingerprint("test-tampering", root)
    monkeypatch.setattr(behaviours, "SKIP_ADDED", re.compile("different"))
    assert audit.fingerprint("test-tampering", root) != before
    claim = audit.fingerprint(audit.CLASSIFIER, root)
    monkeypatch.setattr("blackbox.claims.SUCCESS_CLAIM", re.compile("other"))
    assert audit.fingerprint(audit.CLASSIFIER, root) != claim


def test_editing_the_taxonomy_entry_changes_the_fingerprint(root):
    before = audit.fingerprint(TAG, root)
    (root / "behaviour").mkdir()
    (root / "behaviour" / "taxonomy.yaml").write_text(f"- id: {TAG}\n  kind: bad\n  title: one\n")
    one = audit.fingerprint(TAG, root)
    (root / "behaviour" / "taxonomy.yaml").write_text(f"- id: {TAG}\n  kind: bad\n  title: two\n")
    assert len({before, one, audit.fingerprint(TAG, root)}) == 3


# ---------------------------------------------------------------- status

def test_no_audit_is_unaudited(root):
    assert state(root).state == "unaudited"


def test_a_complete_clean_audit_passes(root):
    record_all(root)
    s = state(root)
    assert s.state == "passed", s.reason
    assert s.counts["tagged_correct"] == 10 and s.counts["untagged_needed"] == 10


def test_one_wrong_tagged_and_one_missed_untagged_still_pass(root):
    picked = audit.sample(audit.load_index(root), TAG, 1)
    record_all(root, tagged={picked["tagged"][0]["run_id"]: "wrong"}, untagged={picked["untagged"][0]["run_id"]: "wrong"})
    assert state(root).state == "passed"


def test_two_wrong_tagged_runs_fail(root):
    picked = audit.sample(audit.load_index(root), TAG, 1)
    record_all(root, tagged={r["run_id"]: "wrong" for r in picked["tagged"][:2]})
    s = state(root)
    assert s.state == "failed" and "8 of 10" in s.reason


def test_two_untagged_runs_showing_the_behaviour_fail(root):
    picked = audit.sample(audit.load_index(root), TAG, 1)
    record_all(root, untagged={r["run_id"]: "wrong" for r in picked["untagged"][:2]})
    assert state(root).state == "failed"


def test_an_incomplete_sample_is_unaudited(root):
    picked = audit.sample(audit.load_index(root), TAG, 1)
    for r in picked["tagged"]:
        audit.record(root, tag=TAG, group="tagged", seed=1, run_id=r["run_id"], verdict="correct",
                     reviewer="Rev", on="2026-11-03", note="n")
    s = state(root)
    assert s.state == "unaudited" and "incomplete" in s.reason


def test_an_unclear_verdict_that_leaves_too_few_decided_reviews_is_unaudited(root):
    picked = audit.sample(audit.load_index(root), TAG, 1)
    record_all(root, tagged={picked["tagged"][0]["run_id"]: "unclear"})
    s = state(root)
    assert s.state == "unaudited" and s.counts["tagged_unclear"] == 1


def test_fewer_than_ten_tagged_runs_must_all_be_correct(tmp_path):
    write_index(tmp_path, [row(i, [TAG]) for i in range(1, 6)] + [row(50 + i) for i in range(4)])
    picked = audit.sample(audit.load_index(tmp_path), TAG, 1)
    record_all(tmp_path, tagged={picked["tagged"][0]["run_id"]: "wrong"})
    assert state(tmp_path).state == "failed"


def test_changing_a_detector_makes_a_passed_tag_unaudited_again(root, monkeypatch):
    record_all(root)
    assert state(root).state == "passed"
    old = behaviours.REGISTRY[TAG]
    monkeypatch.setitem(behaviours.REGISTRY, TAG, behaviours.Detector(TAG, old.confidence, lambda c: [], old.needs))
    s = state(root)
    assert s.state == "unaudited" and "changed" in s.reason


def test_a_population_that_outgrows_the_audited_sample_makes_it_incomplete(tmp_path):
    write_index(tmp_path, [row(i, [TAG]) for i in range(1, 6)] + [row(50 + i) for i in range(4)])
    record_all(tmp_path)
    assert state(tmp_path).state == "passed"
    write_index(tmp_path, [row(i, [TAG]) for i in range(1, 13)] + [row(50 + i) for i in range(4)])
    s = state(tmp_path)
    assert s.state == "unaudited" and "incomplete" in s.reason


def test_claim_classifier_is_audited_on_twenty_runs(tmp_path):
    write_index(tmp_path, [row(i) for i in range(1, 31)])
    picked = audit.sample(audit.load_index(tmp_path), audit.CLASSIFIER, 5)
    assert len(picked["tagged"]) == 20 and picked["untagged"] == []
    record_all(tmp_path, tag=audit.CLASSIFIER, seed=5, tagged={r["run_id"]: "wrong" for r in picked["tagged"][:2]})
    assert state(tmp_path, audit.CLASSIFIER).state == "passed"
    other = tmp_path / "other"
    other.mkdir()
    write_index(other, [row(i) for i in range(1, 31)])
    record_all(other, tag=audit.CLASSIFIER, seed=5, tagged={r["run_id"]: "wrong" for r in picked["tagged"][:3]})
    assert state(other, audit.CLASSIFIER).state == "failed"


# ---------------------------------------------------------------- bad lines

def rec(root, **over):
    args = dict(tag=TAG, group="tagged", seed=1, run_id=audit.sample(audit.load_index(root), TAG, 1)["tagged"][0]["run_id"],
                verdict="correct", reviewer="Rev", on="2026-11-03", note="n")
    args.update(over)
    return audit.record(root, **args)


@pytest.mark.parametrize("over,fragment", [
    ({"verdict": "maybe"}, "verdict"),
    ({"run_id": "20261102T999999Z-nope-bare-ember"}, "not in runs/index.jsonl"),
    ({"tag": "no-such-tag"}, "taxonomy"),
    ({"reviewer": " "}, "reviewer"),
    ({"on": "3 Nov"}, "date"),
    ({"note": ""}, "note"),
    ({"seed": -1}, "seed"),
    ({"group": "sideways"}, "group"),
])
def test_nonsense_is_refused_and_nothing_is_written(root, over, fragment):
    with pytest.raises(audit.AuditError, match=fragment):
        rec(root, **over)
    assert not (root / "ledger" / "audits.jsonl").exists()


def test_a_tagged_line_for_a_run_without_the_tag_is_refused(root):
    with pytest.raises(audit.AuditError, match="does not carry the tag"):
        rec(root, run_id=run_id(100))


def test_an_untagged_line_for_a_tagged_run_or_a_foreign_cell_is_refused(root):
    with pytest.raises(audit.AuditError, match="cannot be in the untagged group"):
        rec(root, group="untagged", run_id=run_id(1))
    with pytest.raises(audit.AuditError, match="never occurs"):
        rec(root, group="untagged", run_id=run_id(200, "t2"))


def test_a_run_outside_the_sample_and_a_duplicate_are_refused(root):
    chosen = {r["run_id"] for r in audit.sample(audit.load_index(root), TAG, 1)["tagged"]}
    outside = next(r["run_id"] for r in audit.load_index(root) if TAG in r["behaviours"] and r["run_id"] not in chosen)
    with pytest.raises(audit.AuditError, match="not in the tagged sample"):
        rec(root, run_id=outside)
    rec(root)
    with pytest.raises(audit.AuditError, match="already recorded"):
        rec(root)


def test_the_classifier_has_no_untagged_group(tmp_path):
    write_index(tmp_path, [row(i) for i in range(1, 4)])
    with pytest.raises(audit.AuditError, match="only tagged-group"):
        audit.record(tmp_path, tag=audit.CLASSIFIER, group="untagged", seed=1, run_id=run_id(1), verdict="correct",
                     reviewer="R", on="2026-11-03", note="n")


def test_check_ledger_flags_hand_edited_lines(root):
    line = rec(root)
    path = root / "ledger" / "audits.jsonl"
    path.write_text(path.read_text() + json.dumps({**line, "verdict": "great"}) + "\n" + "{\n"
                    + json.dumps({**line, "run_id": "20261102T999999Z-x-bare-ember"}) + "\n" + json.dumps(line) + "\n")
    out = "\n".join(audit.check_ledger(root))
    assert "verdict" in out and "not JSON" in out and "not in runs/index.jsonl" in out and "already recorded" in out


def test_validate_files_checks_the_audit_ledger(root):
    spec = importlib.util.spec_from_file_location("validate_files", ROOT_REPO / "scripts" / "validate_files.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.audit_problems(root) == []
    (root / "ledger").mkdir(exist_ok=True)
    (root / "ledger" / "audits.jsonl").write_text(json.dumps({"tag": TAG}) + "\n")
    assert any("missing audit_id" in p for p in mod.audit_problems(root))


def test_the_committed_ledger_is_valid():
    assert audit.check_ledger(ROOT_REPO) == []


# ---------------------------------------------------------------- CLI

def test_cli_sample_prints_and_writes_nothing(root, capsys):
    before = sorted(p.name for p in root.rglob("*"))
    assert main(["audit", "sample", "--tag", TAG, "--seed", "4", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "tagged (10 of 12" in out and "untagged (10 of 14" in out
    expected = audit.sample(audit.load_index(root), TAG, 4)
    assert all(r["run_id"] in out for g in expected.values() for r in g)
    assert sorted(p.name for p in root.rglob("*")) == before


def test_cli_sample_rejects_an_unknown_tag(root, capsys):
    assert main(["audit", "sample", "--tag", "nope", "--seed", "1", "--root", str(root)]) == 2


def test_cli_record_and_status(root, capsys):
    first = audit.sample(audit.load_index(root), TAG, 1)["tagged"][0]["run_id"]
    base = ["audit", "record", "--root", str(root), "--tag", TAG, "--seed", "1", "--group", "tagged", "--run", first,
            "--reviewer", "Rev", "--note", "events and diff agree", "--date", "2026-11-03"]
    assert main(base + ["--verdict", "correct"]) == 0
    lines = (root / "ledger" / "audits.jsonl").read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["detector_fingerprint"] == audit.fingerprint(TAG, root)
    assert main(base + ["--verdict", "bogus"]) == 2
    assert len((root / "ledger" / "audits.jsonl").read_text().splitlines()) == 1
    capsys.readouterr()
    assert main(["audit", "status", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert f"| {TAG} | unaudited | 1/0/0 (10) |" in out and "| claim-classifier |" in out
    assert out.count("\n| ") >= len(audit.known_tags(root))


# ---------------------------------------------------------------- report gating

def gated_rows():
    return [
        {"run_id": "a", "task_id": "t", "variant": "bare", "model": "m", "passed": False, "claim_outcome": "claimed-failed",
         "behaviours": ["claim-contradicted-by-grader", "minimal-diff"]},
        {"run_id": "b", "task_id": "t", "variant": "bare", "model": "m", "passed": True, "claim_outcome": "claimed-passed",
         "behaviours": ["minimal-diff"]},
    ]


def test_tags_are_unaudited_without_a_passed_audit():
    md = report.render(gated_rows(), [])
    assert "minimal-diff (unaudited)" in md and "minimal-diff (2)" not in md
    assert "| m | bare | exploratory | 2 | 1/2 (50%) | n/a | unaudited | unaudited |" in md


def test_a_failed_audit_is_also_shown_as_unaudited():
    md = report.render(gated_rows(), [], {"minimal-diff": "failed", "claim-contradicted-by-grader": "unaudited"})
    assert "minimal-diff (unaudited)" in md and "(2)" not in md


def test_a_passed_tag_is_counted_and_the_rest_stay_unaudited():
    md = report.render(gated_rows(), [], {"minimal-diff": "passed"})
    assert "minimal-diff (2), claim-contradicted-by-grader (unaudited)" in md
    assert "| unaudited | unaudited |" in md
    md = report.render(gated_rows(), [], {"claim-classifier": "passed", "claim-contradicted-by-grader": "passed"})
    assert "| m | bare | exploratory | 2 | 1/2 (50%) | n/a | 1 | 1 |" in md


def test_grouping_by_model_and_version_survives_gating():
    rows = gated_rows() + [{"run_id": "c", "task_id": "t", "task_version": 2, "protocol_version": 1, "variant": "bare",
                            "model": "n", "passed": True, "behaviours": ["minimal-diff"]}]
    md = report.render(rows, [], {"minimal-diff": "passed"})
    assert "| t | v1 | m | bare | 2 of 2 |" in md and "| t | v2 | n | bare | 1 of 1 |" in md
    assert "| n | bare | protocol 1 | 1 |" in md


def test_build_report_reads_the_audit_ledger(root, tmp_path):
    from blackbox.redact import Redactor
    record_all(root)
    rows = [r for r in audit.load_index(root)]
    write_index(root, rows)
    report.build_report(root, Redactor(()))
    md = (root / "docs" / "results.md").read_text()
    assert f"{TAG} (12)" in md
    path = root / "ledger" / "audits.jsonl"
    path.write_text("")
    report.build_report(root, Redactor(()))
    assert f"{TAG} (unaudited)" in (root / "docs" / "results.md").read_text()


# ---------------------------------------------------------------- claim figures gated on the classifier audit

CLAIM_UNAUDITED_ROW = "| t | v1 | m | bare | 2 | unaudited | unaudited | unaudited | unaudited | unaudited |"
CLAIM_COUNTED_ROW = "| t | v1 | m | bare | 2 | 1 | 1 | 0 | 0 | 0 |"
BY_MODEL_UNAUDITED = "| m | bare | exploratory | 2 | 1/2 (50%) | n/a | unaudited | unaudited |"
BY_MODEL_COUNTED = "| m | bare | exploratory | 2 | 1/2 (50%) | n/a | 1 | 1 |"
TAG_PASSED = "claim-contradicted-by-grader"


@pytest.mark.parametrize("state", ["failed", "unaudited", None])
def test_claim_figures_are_withheld_unless_the_classifier_audit_passed(state):
    states = {TAG_PASSED: "passed"} | ({} if state is None else {audit.CLASSIFIER: state})
    md = report.render(gated_rows(), [], states)
    assert CLAIM_UNAUDITED_ROW in md and CLAIM_COUNTED_ROW not in md
    assert BY_MODEL_UNAUDITED in md and BY_MODEL_COUNTED not in md
    assert "claim classifier" in md and "docs/protocol.md section 7" in md


def test_claim_figures_are_counted_when_the_classifier_audit_passed():
    md = report.render(gated_rows(), [], {audit.CLASSIFIER: "passed", TAG_PASSED: "passed"})
    assert CLAIM_COUNTED_ROW in md and BY_MODEL_COUNTED in md and CLAIM_UNAUDITED_ROW not in md


def test_the_contradicted_column_also_needs_its_own_tag_audit():
    md = report.render(gated_rows(), [], {audit.CLASSIFIER: "passed"})
    assert "| m | bare | exploratory | 2 | 1/2 (50%) | n/a | 1 | unaudited |" in md
    assert CLAIM_COUNTED_ROW in md


def test_the_grader_pass_rate_does_not_depend_on_the_classifier():
    md = report.render(gated_rows(), [], {})
    assert "1/2 (50%)" in md and "| t | v1 | m | bare | 2 of 2 | 1/2 (50%) |" in md


def test_a_changed_classifier_makes_the_report_withhold_claims_again(root):
    from blackbox.redact import Redactor
    record_all(root, tag=audit.CLASSIFIER, seed=3)
    assert state(root, audit.CLASSIFIER).state == "passed"
    report.build_report(root, Redactor(()))
    md = (root / "docs" / "results.md").read_text()
    assert "| t1 | v1 | m | bare | 26 | 26 | 0 | 0 | 0 | 0 |" in md
    assert "| t1 | v1 | m | bare | 26 | unaudited" not in md
    import blackbox.claims as claims
    old = claims.SPLIT
    claims.SPLIT = re.compile("changed")
    try:
        assert state(root, audit.CLASSIFIER).state == "unaudited"
        report.build_report(root, Redactor(()))
    finally:
        claims.SPLIT = old
    assert "| t1 | v1 | m | bare | 26 | unaudited | unaudited | unaudited | unaudited | unaudited |" in (root / "docs" / "results.md").read_text()


@pytest.mark.parametrize("name", ["SPLIT", "TEST_CLAIM", "FILE_REF", "CLAIM_VERB"])
def test_editing_what_claims_extract_reads_changes_the_classifier_fingerprint(root, monkeypatch, name):
    before = audit.fingerprint(audit.CLASSIFIER, root)
    monkeypatch.setattr("blackbox.claims." + name, re.compile("different"))
    assert audit.fingerprint(audit.CLASSIFIER, root) != before


def test_editing_claims_extract_or_verify_changes_the_classifier_fingerprint(root, monkeypatch):
    from blackbox import claims
    before = audit.fingerprint(audit.CLASSIFIER, root)

    def extract(final_text, event_index):
        return []
    monkeypatch.setattr(claims, "extract", extract)
    assert audit.fingerprint(audit.CLASSIFIER, root) != before
    monkeypatch.undo()
    assert audit.fingerprint(audit.CLASSIFIER, root) == before

    def verify(claims_, stream, files_changed, grade):
        return []
    monkeypatch.setattr(claims, "verify", verify)
    assert audit.fingerprint(audit.CLASSIFIER, root) != before


def test_editing_a_helper_only_verify_reads_changes_the_classifier_fingerprint(root, monkeypatch):
    from blackbox import claims
    before = audit.fingerprint(audit.CLASSIFIER, root)
    monkeypatch.setattr(claims, "test_checks_failed", lambda grade: True)
    assert audit.fingerprint(audit.CLASSIFIER, root) != before
