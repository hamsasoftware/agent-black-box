import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("incidents", ROOT / "scripts" / "incidents.py")
incidents = importlib.util.module_from_spec(spec)
spec.loader.exec_module(incidents)

PULL = "https://github.com/hexrift/agent-black-box/pull/1"


def entry(**changes):
    base = {
        "id": "INC-001", "date": "2026-11-02", "title": "t", "kind": "harness", "severity": "low", "status": "fixed",
        "root_cause": "missing-test", "introduced_by": "a",
        "agents": [{"name": "Tally", "agent_id": "agt-0a1b2c3d", "role": "introduced"}],
        "introduced_in": {"pr": PULL, "commit": "abc1234", "at": "2026-11-02T10:00:00Z"},
        "detected": {"at": None, "by": "b", "method": "real-run", "how": "c"},
        "fixed": {"pr": PULL, "commit": "def5678", "at": "2026-11-02T10:30:00Z"},
        "exposure_minutes": 30.0, "impact": "d",
        "affected": {"runs": ["r1"], "run_count": 1, "cost_usd": 0.1, "files": ["f"], "tests": ["t"]},
        "why_missed": "w", "evidence": ["e"], "prevention": {"kind": "test", "ref": "r"},
        "invalidates_results": False, "reached_public": False, "public_surface": [], "lesson": "l",
    }
    base.update(copy.deepcopy(changes))
    return base


def test_the_real_log_is_valid_and_its_page_is_current():
    entries = incidents.load()
    assert entries
    assert incidents.problems(entries) == []
    assert (ROOT / "docs" / "incidents.md").read_text(encoding="utf-8") == incidents.render(entries)


def test_agent_ids_in_the_log_exist_in_the_ledger_when_it_is_present():
    ledger = ROOT / "ledger" / "agents.jsonl"
    if not ledger.is_file():
        pytest.skip("ledger not present in this checkout")
    known = {json.loads(line)["agent_id"] for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()}
    cited = {agent["agent_id"] for e in incidents.load() for agent in e["agents"] if agent["agent_id"]}
    assert cited <= known


def test_a_valid_entry_has_no_problems():
    assert incidents.problems([entry()]) == []


@pytest.mark.parametrize("changes, fragment", [
    ({"id": "INC-1"}, "id must look like"),
    ({"date": "2 Nov 2026"}, "date must be"),
    ({"kind": "other"}, "kind must be"),
    ({"severity": "critical"}, "severity must be"),
    ({"status": "wontfix"}, "status must be"),
    ({"root_cause": "bad luck"}, "root_cause must be"),
    ({"reached_public": "no"}, "reached_public must be"),
    ({"invalidates_results": 1}, "invalidates_results must be"),
    ({"title": "  "}, "title must be non-empty"),
    ({"agents": []}, "agents must be a non-empty list"),
    ({"agents": [{"name": "x"}]}, "each agent needs"),
    ({"agents": [{"name": "x", "agent_id": "agt-zz", "role": "r"}]}, "agent_id must look like"),
    ({"introduced_in": {"pr": "no", "commit": "abc1234", "at": None}}, "introduced_in.pr must be"),
    ({"introduced_in": {"pr": PULL, "commit": "XYZ", "at": None}}, "introduced_in.commit must be"),
    ({"introduced_in": {"pr": PULL, "commit": "abc1234", "at": "yesterday"}}, "introduced_in.at must be"),
    ({"introduced_in": {"pr": PULL}}, "introduced_in must be an object"),
    ({"detected": {"at": None, "by": "b", "method": "guess", "how": "c"}}, "detected.method must be"),
    ({"detected": {"by": "b"}}, "detected needs"),
    ({"affected": {"runs": ["r1"], "run_count": 2, "cost_usd": 0.1, "files": [], "tests": []}}, "run_count must equal"),
    ({"affected": {"runs": [], "run_count": 0, "cost_usd": -1, "files": [], "tests": []}}, "cost_usd must be"),
    ({"affected": {"runs": []}}, "affected needs"),
    ({"evidence": []}, "evidence must be a non-empty list"),
    ({"prevention": {"kind": "hope", "ref": "r"}}, "prevention.kind must be"),
    ({"prevention": {"kind": "test", "ref": " "}}, "prevention.ref must be"),
    ({"reached_public": True}, "must name where"),
    ({"public_surface": ["x"]}, "public_surface must be empty"),
    ({"fixed": {"pr": None, "commit": None, "at": None}, "exposure_minutes": None}, "needs fixed.pr"),
    ({"status": "open", "exposure_minutes": 30.0}, "open incident cannot have a fix"),
    ({"exposure_minutes": 31.0}, "exposure_minutes must be 30.0"),
    ({"fixed": {"pr": PULL, "commit": "def5678", "at": "2026-11-02T09:00:00Z"}, "exposure_minutes": -60.0}, "before introduced_in.at"),
])
def test_each_rule_is_enforced(changes, fragment):
    assert any(fragment in line for line in incidents.problems([entry(**changes)])), incidents.problems([entry(**changes)])


def test_exposure_needs_both_times():
    one_sided = entry(introduced_in={"pr": PULL, "commit": "abc1234", "at": None})
    assert any("needs both" in line for line in incidents.problems([one_sided]))
    assert incidents.problems([entry(introduced_in={"pr": PULL, "commit": "abc1234", "at": None}, exposure_minutes=None)]) == []


def test_missing_unknown_and_duplicate_fields_are_reported():
    broken = entry()
    del broken["lesson"]
    assert any("missing lesson" in line for line in incidents.problems([broken]))
    assert any("unknown field extra" in line for line in incidents.problems([entry(extra=1)]))
    assert any("duplicate id" in line for line in incidents.problems([entry(), entry()]))
    assert any("not an object" in line for line in incidents.problems(["text"]))


def test_open_incident_without_fix_is_valid():
    open_entry = entry(status="open", fixed={"pr": None, "commit": None, "at": None}, exposure_minutes=None)
    assert incidents.problems([open_entry]) == []


def test_load_rejects_bad_json_with_the_line_number(tmp_path):
    path = tmp_path / "x.jsonl"
    path.write_text(json.dumps(entry()) + "\n{broken\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        incidents.load(path)


def test_render_escapes_table_cells_counts_runs_and_orders_entries():
    second = entry(id="INC-002", title="a | b", status="open", fixed={"pr": None, "commit": None, "at": None},
                   exposure_minutes=None, reached_public=True, public_surface=["main"], invalidates_results=True,
                   affected={"runs": ["r1", "r2"], "run_count": 2, "cost_usd": None, "files": [], "tests": []})
    page = incidents.render([second, entry()])
    assert "a \\| b" in page
    assert "Incidents: 2. Open: 1. Reached the public repository: 1. Invalidate results: 1. Distinct runs touched by an incident: 2." in page
    assert page.index("## INC-001") < page.index("## INC-002")
    assert "`agt-0a1b2c3d`" in page and "**Run ids:** `r1`, `r2`." in page
    assert "not computable from recorded times" in page and "no code change" in page
    assert "(main)" in page


def test_render_omits_cost_and_links_when_absent():
    page = incidents.render([entry(affected={"runs": [], "run_count": 0, "cost_usd": 0.0, "files": [], "tests": []},
                                   introduced_in={"pr": None, "commit": None, "at": None}, exposure_minutes=None)])
    assert "of run cost" not in page
    assert "no pull request" in page


@pytest.mark.parametrize("changes, fragment", [
    ({"agents": [{"name": "", "agent_id": None, "role": "r"}]}, "agent name and role must be text"),
    ({"fixed": "later"}, "fixed must be an object"),
    ({"detected": {"at": "soon", "by": "b", "method": "real-run", "how": "c"}}, "detected.at must be"),
    ({"detected": {"at": None, "by": " ", "method": "real-run", "how": "c"}}, "detected.by must be non-empty"),
    ({"affected": {"runs": "r1", "run_count": 1, "cost_usd": 0.1, "files": [], "tests": []}}, "affected.runs must be a list"),
    ({"public_surface": "main"}, "public_surface must be a list"),
    ({"prevention": {"kind": "test"}}, "prevention needs kind and ref"),
    ({"fixed": {"pr": PULL, "commit": "def5678", "at": "2026-11-02T10:30:00Z"}, "exposure_minutes": "30"}, "exposure_minutes must be"),
])
def test_malformed_types_are_reported_not_raised(changes, fragment):
    assert any(fragment in line for line in incidents.problems([entry(**changes)])), incidents.problems([entry(**changes)])


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(incidents, "SOURCE", tmp_path / "incidents.jsonl")
    monkeypatch.setattr(incidents, "PAGE", tmp_path / "docs" / "incidents.md")
    monkeypatch.setattr(incidents, "ROOT", tmp_path)
    (tmp_path / "docs").mkdir()
    return tmp_path


def test_main_renders_then_checks_then_detects_a_stale_page(isolated, capsys):
    incidents.SOURCE.write_text(json.dumps(entry()) + "\n", encoding="utf-8")
    assert incidents.main(["check"]) == 1
    assert "out of date" in capsys.readouterr().err
    assert incidents.main(["render"]) == 0
    assert incidents.PAGE.read_text(encoding="utf-8") == incidents.render([entry()])
    assert incidents.main(["check"]) == 0
    assert "valid and the page is current" in capsys.readouterr().out
    incidents.PAGE.write_text("edited by hand", encoding="utf-8")
    assert incidents.main(["check"]) == 1


def test_main_reports_invalid_entries_and_unreadable_input(isolated, capsys):
    incidents.SOURCE.write_text(json.dumps(entry(severity="critical")) + "\n", encoding="utf-8")
    assert incidents.main(["check"]) == 1
    assert "severity must be" in capsys.readouterr().err
    incidents.SOURCE.write_text("{broken\n", encoding="utf-8")
    assert incidents.main(["render"]) == 1
    assert "not valid JSON" in capsys.readouterr().err
    incidents.SOURCE.unlink()
    assert incidents.main(["check"]) == 1


def test_blank_lines_in_the_log_are_ignored(isolated):
    incidents.SOURCE.write_text("\n" + json.dumps(entry()) + "\n\n", encoding="utf-8")
    assert len(incidents.load()) == 1
