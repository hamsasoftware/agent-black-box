from task_helpers import taxonomy

AGREED_BAD = {
    "claim-without-verification", "test-tampering", "scope-creep", "injection-followed",
    "instruction-ignored", "permission-workaround", "hallucinated-api", "premature-stop",
    "thrashing", "secret-exposure", "overengineering", "silent-assumption", "out-of-workspace-access",
}
AGREED_GOOD = {
    "verified-before-claiming", "flagged-ambiguity", "refused-injection", "minimal-diff",
    "stopped-at-block", "test-first", "reproduced-bug-first",
}
FIELDS = {"id", "kind", "title", "description", "why_it_happens", "detector_hint"}


def test_taxonomy_contains_every_agreed_id_with_the_right_kind():
    entries = {e["id"]: e for e in taxonomy()}
    for ident in AGREED_BAD:
        assert entries[ident]["kind"] == "bad", ident
    for ident in AGREED_GOOD:
        assert entries[ident]["kind"] == "good", ident


def test_taxonomy_entries_are_complete_and_unique():
    entries = taxonomy()
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids))
    for entry in entries:
        assert FIELDS <= set(entry), entry["id"]
        assert entry["kind"] in ("good", "bad")
        for field in FIELDS:
            assert isinstance(entry[field], str) and entry[field].strip(), (entry["id"], field)
        extra = set(entry) - FIELDS
        if entry["id"] not in AGREED_BAD | AGREED_GOOD:
            assert extra == {"reason"} and entry["reason"].strip(), entry["id"]
        else:
            assert not extra, entry["id"]


def test_behaviour_readme_lists_and_links_every_id():
    import re

    from task_helpers import ROOT

    readme = (ROOT / "behaviour" / "README.md").read_text()
    lines = (ROOT / "behaviour" / "taxonomy.yaml").read_text().splitlines()
    for number, line in enumerate(lines, 1):
        match = re.match(r"- id: (\S+)", line)
        if match:
            assert f"[`{match.group(1)}`](taxonomy.yaml#L{number})" in readme, match.group(1)


def test_tasks_readme_links_every_task():
    from task_helpers import ROOT, task_ids

    readme = (ROOT / "tasks" / "README.md").read_text()
    for task_id in task_ids():
        assert f"]({task_id}/NOTES.md)" in readme, task_id
