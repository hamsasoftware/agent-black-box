import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_pr_requirements", ROOT / "scripts" / "check_pr_requirements.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

NOREPLY = "123456+someone@users.noreply.github.com"
TEMPLATE = (ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")

GOOD = """## Purpose

Fixes the thing and explains why.

Closes: none (no issue)

## Type of change

- [ ] Bug fix
- [ ] New task
- [ ] Harness or ledger
- [ ] Behaviour catalogue
- [ ] Agent plumbing
- [x] Documentation
- [ ] CI, Makefile or scripts
- [ ] Breaking change

## Evidence

none

## Tests

- `make test`: 10 passed.

## Real-run cost

none

## Checklist

- [x] No secrets are included and `make scan` passed.
- [x] Any committed run data was redacted before commit.
- [x] Documentation is updated where behaviour or usage changed.
- [x] The change contains no unrelated edits.
"""


def event(body=GOOD, title="Fix the thing", branch="fix/the-thing", login="someone"):
    return {"pull_request": {"title": title, "body": body, "head": {"ref": branch}, "user": {"login": login}}}


def commit(author=NOREPLY, committer="noreply@github.com", message="Fix the thing", sha="a" * 40):
    return {"id": sha, "author": author, "committer": committer, "message": message}


def test_a_conforming_pull_request_passes():
    assert check.problems(event(), [commit()]) == []


def test_the_unfilled_template_fails():
    found = check.description_problems("t", TEMPLATE)
    assert any("Purpose must say" in line for line in found)
    assert any("tick at least one" in line for line in found)
    assert any("Evidence must" in line for line in found)
    assert any("Tests must" in line for line in found)
    assert any("Real-run cost" in line for line in found)
    assert any("not ticked" in line for line in found)


def test_the_good_body_is_built_from_the_real_template_headings():
    names, _ = check.sections(TEMPLATE)
    assert tuple(names) == check.SECTIONS
    assert {label for _, label in check.BOX.findall(TEMPLATE)} >= set(check.TYPES) | set(check.CHECKLIST)


@pytest.mark.parametrize("edit, fragment", [
    (lambda b: b.replace("## Evidence\n\nnone\n\n", ""), "must start with these sections"),
    (lambda b: b.replace("## Tests", "## Testing"), "must start with these sections"),
    (lambda b: b.replace("Closes: none (no issue)", ""), "Closes #N"),
    (lambda b: b.replace("Fixes the thing and explains why.\n\n", ""), "Purpose must say"),
    (lambda b: b.replace("- [x] Documentation", "- [ ] Documentation"), "tick at least one"),
    (lambda b: b.replace("- [ ] Breaking change\n", ""), "eight options"),
    (lambda b: b.replace("none\n\n## Tests", "\n\n## Tests"), "Evidence must"),
    (lambda b: b.replace("- `make test`: 10 passed.", ""), "Tests must"),
    (lambda b: b.replace("## Real-run cost\n\nnone", "## Real-run cost\n\nsome"), "Real-run cost must say"),
    (lambda b: b.replace("- [x] The change contains no unrelated edits.", "- [ ] The change contains no unrelated edits."), "not ticked"),
    (lambda b: b.replace("- [x] The change contains no unrelated edits.\n", ""), "must keep the template item"),
])
def test_each_description_rule_is_enforced(edit, fragment):
    found = check.description_problems("t", edit(GOOD))
    assert any(fragment in line for line in found), found


def test_closes_with_an_issue_number_and_a_dollar_cost_are_accepted():
    body = GOOD.replace("Closes: none (no issue)", "Closes #12").replace("## Real-run cost\n\nnone", "## Real-run cost\n\n$0.42 for three runs")
    assert check.description_problems("t", body) == []


def test_an_unticked_item_is_allowed_when_marked_not_applicable():
    body = GOOD.replace("- [x] Any committed run data was redacted before commit.", "- [ ] Any committed run data was redacted before commit. Not applicable: no run data.")
    assert check.description_problems("t", body) == []


def test_a_filled_evidence_table_counts_and_a_blank_one_does_not():
    blank = "| Run id | Task id | Variant | Grader passed | Score |\n|---|---|---|---|---|\n|  |  |  |  |  |"
    filled = blank + "\n| r1 | flaky-backoff | bare | yes | 1.0 |"
    assert not check.filled_evidence(blank)
    assert check.filled_evidence(filled)
    assert check.filled_evidence("see runs/index.jsonl")
    assert not check.filled_evidence("")


def test_html_comments_and_windows_line_endings_are_ignored():
    body = GOOD.replace("## Tests\n", "## Tests\n<!-- note -->\n").replace("\n", "\r\n")
    assert check.description_problems("t", body) == []


@pytest.mark.parametrize("title, body, branch, messages, fragment", [
    ("Add Claude support", GOOD, "fix/x", [], "title contains"),
    ("t", GOOD + "\nGenerated with a tool", "fix/x", [], "description contains"),
    ("t", GOOD, "feat/anthropic-thing", [], "branch name contains"),
    ("t", GOOD, "fix/x", ["fine", "Co-Authored-By: someone"], "commit message 2 contains"),
    ("t", GOOD + "\U0001F916", "fix/x", [], "description contains"),
])
def test_forbidden_wording_is_found_everywhere(title, body, branch, messages, fragment):
    assert any(fragment in line for line in check.wording_problems(title, body, branch, messages))


def test_clean_wording_has_no_problems():
    assert check.wording_problems("Fix it", GOOD, "fix/it", ["Fix it"]) == []


@pytest.mark.parametrize("address", [
    "person@example.com", "someone@users.noreply.github.org", "noreply@example.com", "x@mail.example",
])
def test_private_looking_addresses_fail_for_author_and_committer(address):
    found = check.commit_problems([commit(author=address, committer=address)])
    assert len(found) == 2 and all("no-reply" in line for line in found)


@pytest.mark.parametrize("address", [
    NOREPLY, "someone@users.noreply.github.com", "49699333+dependabot[bot]@users.noreply.github.com", "noreply@github.com",
])
def test_no_reply_addresses_pass(address):
    assert check.commit_problems([commit(author=address, committer=address)]) == []


@pytest.mark.parametrize("branch", ["main", "Fix/Thing", "fix/", "wip", "claude/x", "fix/has_underscore", "feature/x"])
def test_bad_branch_names_fail(branch):
    assert any("branch name must look like" in line for line in check.problems(event(branch=branch), [commit()]))


@pytest.mark.parametrize("branch", ["feat/a", "fix/a-b", "docs/x1", "data/first-matrix", "chore/x", "test/x", "refactor/x", "ci/pr-requirements-check"])
def test_good_branch_names_pass(branch):
    assert not any("branch name must look" in line for line in check.problems(event(branch=branch), [commit()]))


def test_dependabot_is_exempt_from_the_template_but_not_from_wording():
    bot = event(body="Bumps a thing", title="Bump a thing", branch="dependabot/github_actions/x", login="dependabot[bot]")
    assert check.problems(bot, [commit(author="49699333+dependabot[bot]@users.noreply.github.com")]) == []
    assert any("forbidden" in line for line in check.problems(bot, [commit(message="Co-authored-by: x")]))


def test_a_missing_body_is_reported_not_raised():
    assert check.problems({"pull_request": {"title": "t", "head": {"ref": "fix/x"}}}, [commit()])
    assert check.problems({}, [])


def git(repo, *args, env=None):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True,
                          env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", **(env or {})}).stdout


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    return repo


def commit_as(repo, name, message, author, committer):
    (repo / name).write_text(name)
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", message, env={
        "GIT_AUTHOR_NAME": "A", "GIT_AUTHOR_EMAIL": author, "GIT_COMMITTER_NAME": "C", "GIT_COMMITTER_EMAIL": committer})


def test_git_commits_lists_only_the_commits_after_the_base(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    commit_as(repo, "a", "base", NOREPLY, NOREPLY)
    git(repo, "branch", "base")
    commit_as(repo, "b", "first\n\nbody line", NOREPLY, "person@example.com")
    commit_as(repo, "c", "second", NOREPLY, NOREPLY)
    monkeypatch.chdir(repo)
    commits = check.git_commits("base")
    assert [c["message"].strip().split("\n")[0] for c in commits] == ["second", "first"]
    assert commits[1]["committer"] == "person@example.com" and "body line" in commits[1]["message"]
    assert any("committer email" in line for line in check.commit_problems(commits))


def write_event(tmp_path, payload):
    path = tmp_path / "event.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_main_passes_and_fails_through_the_command_line(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path)
    commit_as(repo, "a", "base", NOREPLY, NOREPLY)
    git(repo, "branch", "base")
    commit_as(repo, "b", "Fix the thing", NOREPLY, "noreply@github.com")
    monkeypatch.chdir(repo)
    assert check.main(["--event", write_event(tmp_path, event()), "--base", "base"]) == 0
    assert "meet the requirements" in capsys.readouterr().out
    assert check.main(["--event", write_event(tmp_path, event(body=TEMPLATE)), "--base", "base"]) == 1
    assert "pr-requirements:" in capsys.readouterr().err
    commit_as(repo, "c", "Another", "person@example.com", "person@example.com")
    assert check.main(["--event", write_event(tmp_path, event()), "--base", "base"]) == 1


def test_main_reports_unreadable_input_and_a_bad_base(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path)
    commit_as(repo, "a", "base", NOREPLY, NOREPLY)
    monkeypatch.chdir(repo)
    assert check.main(["--event", str(tmp_path / "missing.json"), "--base", "main"]) == 1
    assert check.main(["--event", write_event(tmp_path, event()), "--base", "no-such-ref"]) == 1
    (tmp_path / "bad.json").write_text("{broken", encoding="utf-8")
    assert check.main(["--event", str(tmp_path / "bad.json"), "--base", "main"]) == 1
    assert capsys.readouterr().err.count("pr-requirements:") == 3
