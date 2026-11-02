#!/usr/bin/env python3
"""Check that a pull request meets the repository's stated requirements.

Checks the description against the pull request template, forbidden wording in the
title, description, branch name and every commit message, and that every commit uses a
GitHub no-reply address for author and committer.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SECTIONS = ("Purpose", "Type of change", "Evidence", "Tests", "Real-run cost", "Checklist")
TYPES = ("Bug fix", "New task", "Harness or ledger", "Behaviour catalogue", "Agent plumbing", "Documentation",
         "CI, Makefile or scripts", "Breaking change")
CHECKLIST = ("No secrets are included and `make scan` passed.", "Any committed run data was redacted before commit.",
             "Documentation is updated where behaviour or usage changed.", "The change contains no unrelated edits.")
FORBIDDEN = re.compile(r"claude|anthropic|generated with|co-authored|\U0001F916", re.IGNORECASE)
BRANCH = re.compile(r"^(feat|fix|docs|data|chore|test|refactor|ci)/[a-z0-9][a-z0-9-]*$")
NOREPLY = re.compile(r"^(\d+\+)?[\w.-]+(\[bot\])?@users\.noreply\.github\.com$|^noreply@github\.com$")
EXEMPT_AUTHORS = {"dependabot[bot]"}
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
CLOSES = re.compile(r"^Closes:?\s*(#\d+|none\b.*)$", re.IGNORECASE | re.MULTILINE)
BOX = re.compile(r"^- \[([ xX])\] (.+?)\s*$", re.MULTILINE)
TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")


def sections(body: str) -> tuple[list[str], dict[str, str]]:
    text = COMMENT.sub("", body.replace("\r\n", "\n"))
    names: list[str] = []
    parts: dict[str, list[str]] = {}
    current = None
    for line in text.split("\n"):
        match = re.match(r"^## (.+?)\s*$", line)
        if match:
            current = match.group(1)
            names.append(current)
            parts[current] = []
        elif current is not None:
            parts[current].append(line)
    return names, {name: "\n".join(lines).strip() for name, lines in parts.items()}


def filled_evidence(text: str) -> bool:
    rows = [line for line in text.split("\n") if line.strip()]
    for line in rows:
        if TABLE_ROW.match(line):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if all(set(cell) <= set("-: ") for cell in cells) or not any(cells):
                continue
            if cells and cells[0].lower() == "run id":
                continue
            return True
        return True
    return False


def description_problems(title: str, body: str) -> list[str]:
    found: list[str] = []
    names, parts = sections(body or "")
    if [name for name in names if name in SECTIONS] != list(SECTIONS):
        return [f"description must contain these sections once each and in this order, with extra sections allowed between them: {', '.join(SECTIONS)}"]
    purpose = re.sub(r"^Closes.*$", "", parts["Purpose"], flags=re.IGNORECASE | re.MULTILINE).strip()
    if not purpose:
        found.append("Purpose must say what the change does and why")
    if not CLOSES.search(parts["Purpose"]):
        found.append("Purpose must contain a line 'Closes #N' or 'Closes: none'")
    boxes = {label: mark.lower() == "x" for mark, label in BOX.findall(parts["Type of change"])}
    if set(boxes) != set(TYPES):
        found.append("Type of change must keep the template's eight options")
    elif not any(boxes.values()):
        found.append("Type of change must tick at least one option")
    if not filled_evidence(parts["Evidence"]):
        found.append("Evidence must list runs or say none")
    if not parts["Tests"]:
        found.append("Tests must list the commands run and their results")
    cost = parts["Real-run cost"]
    if not (re.search(r"\bnone\b", cost, re.IGNORECASE) or re.search(r"\$\s?\d", cost)):
        found.append("Real-run cost must say none or give a dollar amount")
    lines = [(mark.lower() == "x", text) for mark, text in BOX.findall(parts["Checklist"])]
    for label in CHECKLIST:
        match = next(((ticked, text) for ticked, text in lines if text.startswith(label)), None)
        if match is None:
            found.append(f"Checklist must keep the template item: {label}")
        elif not match[0] and "not applicable" not in match[1].lower():
            found.append(f"Checklist item not ticked and not marked not applicable: {label}")
    return found


def wording_problems(title: str, body: str, branch: str, messages: list[str]) -> list[str]:
    found = []
    for name, text in (("title", title), ("description", body), ("branch name", branch)):
        if FORBIDDEN.search(text or ""):
            found.append(f"{name} contains forbidden wording")
    for index, message in enumerate(messages, 1):
        if FORBIDDEN.search(message):
            found.append(f"commit message {index} contains forbidden wording")
    return found


def commit_problems(commits: list[dict]) -> list[str]:
    found = []
    for commit in commits:
        for role in ("author", "committer"):
            if not NOREPLY.match(commit[role]):
                found.append(f"commit {commit['id'][:7]}: {role} email must be a GitHub no-reply address")
    return found


def git_commits(base: str, head: str = "HEAD") -> list[dict]:
    raw = subprocess.run(["git", "log", f"{base}..{head}", "--format=%H%x1f%ae%x1f%ce%x1f%B%x1e"],
                         capture_output=True, text=True, check=True).stdout
    commits = []
    for record in raw.split("\x1e"):
        if record.strip():
            sha, author, committer, message = record.strip("\n").split("\x1f", 3)
            commits.append({"id": sha.strip(), "author": author, "committer": committer, "message": message})
    return commits


def problems(event: dict, commits: list[dict]) -> list[str]:
    pull = event.get("pull_request") or {}
    title, body = pull.get("title") or "", pull.get("body") or ""
    branch = (pull.get("head") or {}).get("ref") or ""
    if (pull.get("user") or {}).get("login") in EXEMPT_AUTHORS:
        return wording_problems(title, "", branch, [commit["message"] for commit in commits])
    found = description_problems(title, body)
    found += wording_problems(title, body, branch, [commit["message"] for commit in commits])
    if not BRANCH.match(branch):
        found.append("branch name must look like type/short-topic, with type one of feat, fix, docs, data, chore, test, refactor, ci")
    found += commit_problems(commits)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True, help="path to the pull request event payload")
    parser.add_argument("--base", required=True, help="base ref to list commits from, for example origin/main")
    args = parser.parse_args(argv)
    try:
        event = json.loads(Path(args.event).read_text(encoding="utf-8"))
        commits = git_commits(args.base)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"pr-requirements: {error}", file=sys.stderr)
        return 1
    found = problems(event, commits)
    if found:
        print("\n".join(f"pr-requirements: {line}" for line in found), file=sys.stderr)
        return 1
    print(f"pr-requirements: description, wording, branch and {len(commits)} commit(s) meet the requirements")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
