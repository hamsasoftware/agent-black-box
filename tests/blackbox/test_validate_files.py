import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("validate_files", ROOT / "scripts" / "validate_files.py")
validate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate)

TAXONOMY = "- id: alpha\n  kind: bad\n- id: beta\n  kind: good\n"


def form(options: list[str]) -> str:
    lines = "".join(f"        - {name}\n" for name in options)
    return (
        "name: Behaviour report\nbody:\n  - type: dropdown\n    id: taxonomy-id\n    attributes:\n"
        f"      label: Taxonomy id\n      options:\n{lines}"
    )


@pytest.fixture()
def site(tmp_path, monkeypatch):
    forms = tmp_path / "forms"
    forms.mkdir()
    taxonomy = tmp_path / "taxonomy.yaml"
    taxonomy.write_text(TAXONOMY, encoding="utf-8")
    monkeypatch.setattr(validate, "FORM_DIR", forms)
    monkeypatch.setattr(validate, "TAXONOMY", taxonomy)
    return forms, taxonomy


def test_a_form_that_matches_the_taxonomy_has_no_problems(site):
    forms, _ = site
    (forms / "report.yml").write_text(form(["alpha", "beta", "other"]), encoding="utf-8")
    assert validate.taxonomy_problems() == []


def test_a_behaviour_missing_from_the_dropdown_is_reported(site):
    forms, _ = site
    (forms / "report.yml").write_text(form(["alpha", "other"]), encoding="utf-8")
    problems = validate.taxonomy_problems()
    assert len(problems) == 1 and "taxonomy id beta is not in the dropdown" in problems[0]


def test_a_dropdown_option_the_catalogue_does_not_define_is_reported(site):
    forms, _ = site
    (forms / "report.yml").write_text(form(["alpha", "beta", "invented", "other"]), encoding="utf-8")
    problems = validate.taxonomy_problems()
    assert len(problems) == 1 and "dropdown option invented is not in" in problems[0]


def test_other_is_always_allowed(site):
    forms, _ = site
    (forms / "report.yml").write_text(form(["alpha", "beta"]), encoding="utf-8")
    assert validate.taxonomy_problems() == []


def test_forms_without_the_taxonomy_field_are_ignored(site):
    forms, _ = site
    (forms / "other.yml").write_text("name: x\nbody:\n  - type: input\n    id: something\n", encoding="utf-8")
    assert validate.taxonomy_problems() == []


def test_no_taxonomy_file_means_nothing_to_compare(site):
    _, taxonomy = site
    taxonomy.unlink()
    assert validate.taxonomy_problems() == []


def test_a_taxonomy_with_no_ids_is_a_problem(site):
    _, taxonomy = site
    taxonomy.write_text("[]\n", encoding="utf-8")
    assert "no ids found" in validate.taxonomy_problems()[0]


def test_main_fails_when_the_form_drifts_from_the_catalogue(site, monkeypatch, capsys):
    forms, _ = site
    (forms / "report.yml").write_text(form(["alpha", "other"]), encoding="utf-8")
    monkeypatch.setattr(validate, "tracked_files", lambda: [])
    assert validate.main() == 1
    assert "problem: " in capsys.readouterr().out


def test_the_real_repository_is_consistent(monkeypatch):
    monkeypatch.chdir(ROOT)
    assert validate.taxonomy_problems() == []
    assert validate.main() == 0
