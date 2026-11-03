"""The pinned specification of a task: its rules, its declared checks, its version and its content hash.

docs/protocol.md section 3 and 8 explain why. This module is used by the runner (to compile the prompt and record
the version and hash), by `scripts/task_lock.py` (to freeze a task) and by the criteria tests (gate G1).
"""
from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path
from typing import Any

import yaml

PROTOCOL_VERSION = 1
CLASSES = ("rule", "result", "trap", "advisory")
HASHED = ("task.yaml", "PROMPT.md", "NOTES.md", "grader", "fixture")
SKIP = {"__pycache__", ".pytest_cache", ".git"}
RESERVED = {"grader-error"}  # emitted by every grader's entry point if the grader itself crashes; never a task criterion
RULES_HEADING = "Rules for this task:"
NOTES_HEADINGS = ("## Criteria", "## Hidden by design", "## Version history")


def _files(path: Path):
    if path.is_file():
        yield path
    elif path.is_dir():
        for child in sorted(path.rglob("*")):
            if child.is_file() and not (set(child.parts) & SKIP) and child.suffix != ".pyc":
                yield child


def task_sha256(task_dir: Path) -> str:
    """Hash of every file that defines the task, by relative path and bytes, in a fixed order."""
    digest = hashlib.sha256()
    for name in HASHED:
        for file in _files(task_dir / name):
            digest.update(file.relative_to(task_dir).as_posix().encode() + b"\0")
            digest.update(file.read_bytes() + b"\0")
    return digest.hexdigest()


def load_spec(task_dir: Path) -> dict[str, Any]:
    return yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf-8")) or {}


def rules_block(task: dict[str, Any]) -> str:
    lines = [str(rule["text"]).strip() for rule in task.get("rules") or [] if isinstance(rule, dict) and rule.get("text")]
    return "" if not lines else RULES_HEADING + "\n" + "\n".join(f"- {line}" for line in lines) + "\n"


def compile_prompt(task: dict[str, Any], prompt: str) -> str:
    """PROMPT.md followed by the rules block. Tasks without rules are sent unchanged."""
    block = rules_block(task)
    return prompt if not block else prompt.rstrip("\n") + "\n\n" + block


def grader_checks(grader: Path) -> tuple[set[str], set[str]]:
    """Every check name the grader can add, and the names it adds with required=False."""
    names: set[str] = set()
    advisory: set[str] = set()
    for node in ast.walk(ast.parse(grader.read_text(encoding="utf-8"))):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add"):
            continue
        if not (node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
            continue
        name = node.args[0].value
        names.add(name)
        for keyword in node.keywords:
            if keyword.arg == "required" and isinstance(keyword.value, ast.Constant) and keyword.value.value is False:
                advisory.add(name)
    return names, advisory


def pilot_approved(task_dir: Path, version: int) -> bool:
    """Gate G3: PILOT.md has a section for this version whose verdict is approved."""
    path = task_dir / "PILOT.md"
    if not path.is_file():
        return False
    match = re.search(rf"^## v{version}\b(.*?)(?=^## |\Z)", path.read_text(encoding="utf-8"), flags=re.MULTILINE | re.DOTALL)
    return bool(match and re.search(r"^- Verdict: approved\s*$", match.group(1), flags=re.MULTILINE))


def _section(notes: str, heading: str) -> str:
    match = re.search(rf"^{re.escape(heading)}\s*$(.*?)(?=^## |\Z)", notes, flags=re.MULTILINE | re.DOTALL)
    return match.group(1) if match else ""


def check_spec(task_dir: Path, solutions_dir: Path | None = None) -> list[str]:
    """Problems with a task's declared criteria (gate G1). An empty list means the criteria are complete."""
    problems: list[str] = []
    task = load_spec(task_dir)
    prompt = (task_dir / "PROMPT.md").read_text(encoding="utf-8")
    version = task.get("version")
    if not (isinstance(version, int) and not isinstance(version, bool) and version >= 1):
        problems.append("version must be a whole number of at least 1")

    if not isinstance(task.get("frozen"), bool):
        problems.append("frozen must be true or false")

    rules = task.get("rules")
    rule_ids: dict[str, dict[str, Any]] = {}
    if not (isinstance(rules, list) and rules):
        problems.append("rules must be a non-empty list")
        rules = []
    for rule in rules:
        rid = rule.get("id") if isinstance(rule, dict) else None
        if not (isinstance(rid, str) and rid):
            problems.append("every rule needs an id")
            continue
        if rid in rule_ids:
            problems.append(f"rule {rid} is declared twice")
        rule_ids[rid] = rule
        text, quote = rule.get("text"), rule.get("quote")
        if bool(text) == bool(quote):
            problems.append(f"rule {rid} needs exactly one of text or quote")
        elif quote and quote not in prompt:
            problems.append(f"rule {rid} quotes a sentence that is not in PROMPT.md: {quote!r}")
    scope = task.get("scope") or []
    if scope:
        scope_rule = rule_ids.get("scope")
        shown = str((scope_rule or {}).get("text") or (scope_rule or {}).get("quote") or "")
        if scope_rule is None:
            problems.append("a task with a scope needs a rule with id scope")
        for pattern in scope:
            token = pattern[:-2] if pattern.endswith("/*") else pattern
            if scope_rule is not None and token not in shown:
                problems.append(f"the scope rule does not mention {token}")

    declared = task.get("checks")
    by_name: dict[str, dict[str, Any]] = {}
    if not (isinstance(declared, list) and declared):
        problems.append("checks must be a non-empty list")
        declared = []
    for check in declared:
        name = check.get("name") if isinstance(check, dict) else None
        if not (isinstance(name, str) and name):
            problems.append("every check needs a name")
            continue
        if name in by_name:
            problems.append(f"check {name} is declared twice")
        by_name[name] = check
        if check.get("class") not in CLASSES:
            problems.append(f"check {name} needs a class from {', '.join(CLASSES)}")
        if not str(check.get("why") or "").strip():
            problems.append(f"check {name} needs a why")
        if check.get("class") == "rule" and check.get("rule") not in rule_ids:
            problems.append(f"rule check {name} must name a declared rule")

    grader_names, grader_advisory = grader_checks(task_dir / "grader" / "run.py")
    grader_names -= RESERVED
    grader_advisory -= RESERVED
    for name in sorted(grader_names - set(by_name)):
        problems.append(f"the grader emits {name}, which is not declared")
    for name, check in by_name.items():
        if name not in grader_names and not check.get("conditional"):
            problems.append(f"{name} is declared but the grader never emits it (mark it conditional if it only appears on a crash)")
    declared_advisory = {n for n, c in by_name.items() if c.get("class") == "advisory"}
    for name in sorted((grader_advisory - declared_advisory) & set(by_name)):
        problems.append(f"{name} is advisory in the grader but not declared advisory")
    for name in sorted((declared_advisory - grader_advisory) & grader_names):
        problems.append(f"{name} is declared advisory but the grader requires it")

    notes = (task_dir / "NOTES.md").read_text(encoding="utf-8")
    for heading in NOTES_HEADINGS:
        if heading not in notes:
            problems.append(f"NOTES.md lacks the section {heading}")
    hidden = _section(notes, "## Hidden by design")
    for name, check in by_name.items():
        if check.get("class") == "trap" and name not in hidden:
            problems.append(f"trap check {name} is not listed under Hidden by design in NOTES.md")
    history = _section(notes, "## Version history")
    if isinstance(version, int) and f"v{version}" not in history:
        problems.append(f"NOTES.md version history has no entry for v{version}")

    alternatives = task.get("alternatives")
    if not (isinstance(alternatives, list) and alternatives):
        problems.append("alternatives must list at least one alternative good solution")
        alternatives = []
    for alt in alternatives:
        name = alt.get("name") if isinstance(alt, dict) else None
        if not (isinstance(name, str) and name and str(alt.get("why") or "").strip()):
            problems.append("every alternative needs a name and a why")
        elif solutions_dir is not None and not (solutions_dir / task.get("id", "") / name).is_dir():
            problems.append(f"alternative {name} has no solution directory")
    return problems
