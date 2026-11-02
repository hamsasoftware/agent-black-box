#!/usr/bin/env python3
"""Validate ledger/incidents.jsonl and render docs/incidents.md from it."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "ledger" / "incidents.jsonl"
PAGE = ROOT / "docs" / "incidents.md"

KINDS = {"process", "harness", "detector", "ci", "docs", "task", "agent-behaviour"}
SEVERITIES = {"low", "medium", "high"}
STATUSES = {"open", "fixed", "accepted"}
ROOT_CAUSES = {"requirement-gap", "missing-test", "no-owner", "tool-behaviour", "agent-error", "process-gap", "permission-layer"}
METHODS = {"compliance-check", "manual-inspection", "real-run", "review", "self-report", "tests", "ci"}
PREVENTION_KINDS = {"test", "ci-check", "process", "doc", "none"}
FIELDS = ("id", "date", "title", "kind", "severity", "status", "root_cause", "introduced_by", "agents", "introduced_in",
          "detected", "fixed", "exposure_minutes", "impact", "affected", "why_missed", "evidence", "prevention",
          "invalidates_results", "reached_public", "public_surface", "lesson")
TEXT_FIELDS = ("title", "introduced_by", "impact", "why_missed", "lesson")
ID = re.compile(r"^INC-\d{3}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
PULL = re.compile(r"^https://github\.com/[\w.-]+/[\w.-]+/pull/\d+$")
COMMIT = re.compile(r"^[0-9a-f]{7,40}$")
AGENT_ID = re.compile(r"^agt-[0-9a-f]{8}$")


def load(path: Path | None = None) -> list[dict]:
    path = SOURCE if path is None else path
    entries = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(f"line {number}: not valid JSON ({error.msg})") from error
    return entries


def _minutes(start: str, end: str) -> float:
    parse = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
    return round((parse(end) - parse(start)).total_seconds() / 60, 1)


def _event(label: str, name: str, value: object, found: list[str], with_pr: bool = True) -> None:
    keys = {"pr", "commit", "at"} if with_pr else None
    if not isinstance(value, dict) or (keys is not None and set(value) != keys):
        found.append(f"{label}: {name} must be an object with pr, commit and at")
        return
    if value["pr"] is not None and not (isinstance(value["pr"], str) and PULL.match(value["pr"])):
        found.append(f"{label}: {name}.pr must be a pull request URL or null")
    if value["commit"] is not None and not (isinstance(value["commit"], str) and COMMIT.match(value["commit"])):
        found.append(f"{label}: {name}.commit must be a hex commit id or null")
    if value["at"] is not None and not (isinstance(value["at"], str) and STAMP.match(value["at"])):
        found.append(f"{label}: {name}.at must be YYYY-MM-DDTHH:MM:SSZ or null")


def problems(entries: list[dict]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries, 1):
        label = entry.get("id", f"entry {index}") if isinstance(entry, dict) else f"entry {index}"
        if not isinstance(entry, dict):
            found.append(f"{label}: not an object")
            continue
        missing = [name for name in FIELDS if name not in entry]
        extra = [name for name in entry if name not in FIELDS]
        if missing:
            found.append(f"{label}: missing {', '.join(missing)}")
        if extra:
            found.append(f"{label}: unknown field {', '.join(extra)}")
        if missing:
            continue
        if not ID.match(str(entry["id"])):
            found.append(f"{label}: id must look like INC-001")
        if entry["id"] in seen:
            found.append(f"{label}: duplicate id")
        seen.add(entry["id"])
        if not DATE.match(str(entry["date"])):
            found.append(f"{label}: date must be YYYY-MM-DD")
        for name, allowed in (("kind", KINDS), ("severity", SEVERITIES), ("status", STATUSES), ("root_cause", ROOT_CAUSES)):
            if entry[name] not in allowed:
                found.append(f"{label}: {name} must be one of {sorted(allowed)}")
        for name in ("reached_public", "invalidates_results"):
            if not isinstance(entry[name], bool):
                found.append(f"{label}: {name} must be true or false")
        for name in TEXT_FIELDS:
            if not isinstance(entry[name], str) or not entry[name].strip():
                found.append(f"{label}: {name} must be non-empty text")
        agents = entry["agents"]
        if not isinstance(agents, list) or not agents:
            found.append(f"{label}: agents must be a non-empty list")
        else:
            for agent in agents:
                if not (isinstance(agent, dict) and set(agent) == {"name", "agent_id", "role"}):
                    found.append(f"{label}: each agent needs name, agent_id and role")
                    continue
                if not (isinstance(agent["name"], str) and agent["name"].strip() and isinstance(agent["role"], str) and agent["role"].strip()):
                    found.append(f"{label}: agent name and role must be text")
                if agent["agent_id"] is not None and not (isinstance(agent["agent_id"], str) and AGENT_ID.match(agent["agent_id"])):
                    found.append(f"{label}: agent_id must look like agt-1a2b3c4d or be null")
        _event(label, "introduced_in", entry["introduced_in"], found)
        _event(label, "fixed", entry["fixed"], found)
        detected = entry["detected"]
        if not (isinstance(detected, dict) and set(detected) == {"at", "by", "method", "how"}):
            found.append(f"{label}: detected needs at, by, method and how")
        else:
            if detected["at"] is not None and not (isinstance(detected["at"], str) and STAMP.match(detected["at"])):
                found.append(f"{label}: detected.at must be YYYY-MM-DDTHH:MM:SSZ or null")
            if detected["method"] not in METHODS:
                found.append(f"{label}: detected.method must be one of {sorted(METHODS)}")
            for name in ("by", "how"):
                if not isinstance(detected[name], str) or not detected[name].strip():
                    found.append(f"{label}: detected.{name} must be non-empty text")
        affected = entry["affected"]
        if not (isinstance(affected, dict) and set(affected) == {"runs", "run_count", "cost_usd", "files", "tests"}):
            found.append(f"{label}: affected needs runs, run_count, cost_usd, files and tests")
        else:
            for name in ("runs", "files", "tests"):
                if not (isinstance(affected[name], list) and all(isinstance(item, str) and item for item in affected[name])):
                    found.append(f"{label}: affected.{name} must be a list of text")
            if isinstance(affected["runs"], list) and affected["run_count"] != len(affected["runs"]):
                found.append(f"{label}: affected.run_count must equal the number of runs listed")
            cost = affected["cost_usd"]
            if cost is not None and not (isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= 0):
                found.append(f"{label}: affected.cost_usd must be a non-negative number or null")
        if not (isinstance(entry["evidence"], list) and entry["evidence"] and all(isinstance(item, str) and item.strip() for item in entry["evidence"])):
            found.append(f"{label}: evidence must be a non-empty list of text")
        prevention = entry["prevention"]
        if not (isinstance(prevention, dict) and set(prevention) == {"kind", "ref"}):
            found.append(f"{label}: prevention needs kind and ref")
        else:
            if prevention["kind"] not in PREVENTION_KINDS:
                found.append(f"{label}: prevention.kind must be one of {sorted(PREVENTION_KINDS)}")
            if not isinstance(prevention["ref"], str) or not prevention["ref"].strip():
                found.append(f"{label}: prevention.ref must be non-empty text")
        surface = entry["public_surface"]
        if not (isinstance(surface, list) and all(isinstance(item, str) and item for item in surface)):
            found.append(f"{label}: public_surface must be a list of text")
        elif entry["reached_public"] is True and not surface:
            found.append(f"{label}: an incident that reached the public repository must name where")
        elif entry["reached_public"] is False and surface:
            found.append(f"{label}: public_surface must be empty when reached_public is false")
        fixed = entry["fixed"]
        if isinstance(fixed, dict) and entry["status"] == "fixed" and not (fixed.get("pr") and fixed.get("commit") and fixed.get("at")):
            found.append(f"{label}: a fixed incident needs fixed.pr, fixed.commit and fixed.at")
        if entry["status"] == "open" and isinstance(fixed, dict) and any(fixed.get(name) for name in ("pr", "commit", "at")):
            found.append(f"{label}: an open incident cannot have a fix")
        intro = entry["introduced_in"]
        both_times = (isinstance(intro, dict) and isinstance(fixed, dict) and isinstance(intro.get("at"), str)
                      and isinstance(fixed.get("at"), str) and STAMP.match(intro["at"]) and STAMP.match(fixed["at"]))
        if both_times:
            expected = _minutes(intro["at"], fixed["at"])
            if entry["exposure_minutes"] != expected:
                found.append(f"{label}: exposure_minutes must be {expected}")
            if expected < 0:
                found.append(f"{label}: fixed.at is before introduced_in.at")
        elif entry["exposure_minutes"] is not None:
            found.append(f"{label}: exposure_minutes needs both introduced_in.at and fixed.at")
    return found


def cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _link(label: str, url: str | None) -> str:
    return f"[{label}]({url})" if url else label


def render(entries: list[dict]) -> str:
    ordered = sorted(entries, key=lambda entry: entry["id"])
    touched = {run for entry in ordered for run in entry["affected"]["runs"]}
    lines = [
        "# Incident log",
        "",
        "Generated by `python scripts/incidents.py render` from [ledger/incidents.jsonl](../ledger/incidents.jsonl). Do not edit by hand.",
        "",
        "Every error found while building or running this repository is recorded here: who introduced it, who found it, how, what it affected, what it cost and what now prevents it. The aim is to learn from mistakes, not to assign blame. Agents are named as the ledger names them. A blank time means it was not recorded and is not guessed.",
        "",
        f"Incidents: {len(ordered)}. Open: {sum(e['status'] == 'open' for e in ordered)}. Reached the public repository: {sum(e['reached_public'] for e in ordered)}. "
        f"Invalidate results: {sum(e['invalidates_results'] for e in ordered)}. Distinct runs touched by an incident: {len(touched)}.",
        "",
        "| Id | Severity | Title | Root cause | Introduced by | Found by | Exposure (min) | Affected runs | Status |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for entry in ordered:
        exposure = "" if entry["exposure_minutes"] is None else f"{entry['exposure_minutes']:g}"
        lines.append(
            f"| [{entry['id']}](#{entry['id'].lower()}) | {entry['severity']} | {cell(entry['title'])} | {entry['root_cause']} | "
            f"{cell(entry['introduced_by'])} | {cell(entry['detected']['by'])} | {exposure} | {entry['affected']['run_count']} | {entry['status']} |"
        )
    for entry in ordered:
        intro, fixed, detected, affected = entry["introduced_in"], entry["fixed"], entry["detected"], entry["affected"]
        lines += [
            "",
            f"## {entry['id']}",
            "",
            f"**{entry['title']}**",
            "",
            f"- **Kind, severity, status, root cause:** {entry['kind']}, {entry['severity']}, {entry['status']}, {entry['root_cause']}.",
            f"- **Invalidates results:** {'yes' if entry['invalidates_results'] else 'no'}. **Reached the public repository:** {'yes' if entry['reached_public'] else 'no'}"
            + (f" ({'; '.join(entry['public_surface'])})." if entry["public_surface"] else "."),
            "- **Agents:** " + "; ".join(
                f"{agent['name']}{' `' + agent['agent_id'] + '`' if agent['agent_id'] else ''} ({agent['role']})" for agent in entry["agents"]) + ".",
            f"- **Introduced:** {entry['introduced_by']}. In {_link('pull request', intro['pr']) if intro['pr'] else 'no pull request'}"
            + (f", commit `{intro['commit']}`" if intro["commit"] else "") + (f", at {intro['at']}" if intro["at"] else "") + ".",
            f"- **Detected:** by {detected['by']} ({detected['method']})" + (f" at {detected['at']}" if detected["at"] else "") + f". {detected['how']}",
            "- **Fixed:** " + (
                f"{_link('pull request', fixed['pr'])}, commit `{fixed['commit']}`, at {fixed['at']}." if fixed["pr"] else "no code change."),
            f"- **Exposure:** {entry['exposure_minutes']:g} minutes between introduction and fix." if entry["exposure_minutes"] is not None
            else "- **Exposure:** not computable from recorded times.",
            f"- **Impact:** {entry['impact']}",
            f"- **Affected:** {affected['run_count']} runs"
            + (f", ${affected['cost_usd']:.4f} of run cost" if affected["cost_usd"] else "")
            + (f"; files: {', '.join('`' + item + '`' for item in affected['files'])}" if affected["files"] else "")
            + (f"; tests: {', '.join('`' + item + '`' for item in affected['tests'])}" if affected["tests"] else "") + ".",
            f"- **Why it was missed:** {entry['why_missed']}",
            "- **Evidence:** " + "; ".join(entry["evidence"]) + ".",
            f"- **Prevention ({entry['prevention']['kind']}):** {entry['prevention']['ref']}.",
            f"- **Lesson:** {entry['lesson']}",
        ]
        if affected["runs"]:
            lines += ["- **Run ids:** " + ", ".join(f"`{run}`" for run in affected["runs"]) + "."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "render"))
    args = parser.parse_args(argv)
    try:
        entries = load()
    except (OSError, ValueError) as error:
        print(f"incidents: {error}", file=sys.stderr)
        return 1
    found = problems(entries)
    if found:
        print("\n".join(f"incidents: {line}" for line in found), file=sys.stderr)
        return 1
    text = render(entries)
    if args.command == "render":
        PAGE.write_text(text, encoding="utf-8")
        print(f"incidents: wrote {PAGE.relative_to(ROOT)} ({len(entries)} entries)")
        return 0
    if not PAGE.exists() or PAGE.read_text(encoding="utf-8") != text:
        print("incidents: docs/incidents.md is out of date; run python scripts/incidents.py render", file=sys.stderr)
        return 1
    print(f"incidents: {len(entries)} entries valid and the page is current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
