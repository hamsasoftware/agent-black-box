#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

import yaml

FORM_DIR = Path(".github/ISSUE_TEMPLATE")
TAXONOMY = Path("behaviour/taxonomy.yaml")
TAXONOMY_FIELD = "taxonomy-id"


def tracked_files():
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        check=True, capture_output=True,
    ).stdout
    return [Path(n) for n in out.decode().split("\0") if n and Path(n).is_file()]


def check_parse(path):
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in (".yml", ".yaml"):
        list(yaml.safe_load_all(text))
    elif suffix == ".json":
        json.loads(text)
    elif suffix == ".jsonl":
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.strip():
                try:
                    json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"line {lineno}: {exc}") from exc


def check_form(path):
    errors = []
    form = yaml.safe_load(path.read_text(encoding="utf-8"))
    if path.name == "config.yml":
        if form.get("blank_issues_enabled") is not False:
            errors.append("blank_issues_enabled must be false")
        for link in form.get("contact_links", []):
            for key in ("name", "url", "about"):
                if not link.get(key):
                    errors.append(f"contact link missing {key}")
        return errors
    for key in ("name", "description", "body"):
        if not form.get(key):
            errors.append(f"missing top-level {key}")
    ids = set()
    for item in form.get("body", []):
        kind = item.get("type")
        if kind not in ("markdown", "textarea", "input", "dropdown", "checkboxes"):
            errors.append(f"unknown body type {kind!r}")
        attrs = item.get("attributes") or {}
        if kind != "markdown":
            if not item.get("id"):
                errors.append(f"{kind} field without id")
            elif item["id"] in ids:
                errors.append(f"duplicate id {item['id']}")
            ids.add(item.get("id"))
            if not attrs.get("label"):
                errors.append(f"field {item.get('id')} has no label")
        if kind in ("dropdown", "checkboxes"):
            options = attrs.get("options") or []
            if not options:
                errors.append(f"field {item.get('id')} has no options")
            if kind == "dropdown" and len(set(options)) != len(options):
                errors.append(f"field {item.get('id')} has duplicate options")
    return errors


def collect_ids(node, found):
    if isinstance(node, dict):
        if isinstance(node.get("id"), str):
            found.add(node["id"])
        for value in node.values():
            collect_ids(value, found)
    elif isinstance(node, list):
        for value in node:
            collect_ids(value, found)


def taxonomy_warnings():
    if not TAXONOMY.is_file():
        return []
    known = set()
    collect_ids(yaml.safe_load(TAXONOMY.read_text(encoding="utf-8")), known)
    if not known:
        return [f"{TAXONOMY}: no ids found"]
    warnings = []
    for path in sorted(FORM_DIR.glob("*.yml")):
        form = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for item in form.get("body", []) or []:
            if item.get("id") != TAXONOMY_FIELD:
                continue
            options = set(item.get("attributes", {}).get("options", [])) - {"other"}
            for missing in sorted(known - options):
                warnings.append(f"{path}: taxonomy id {missing} is not in the dropdown")
            for extra in sorted(options - known):
                warnings.append(f"{path}: dropdown option {extra} is not in {TAXONOMY}")
    return warnings


def main():
    strict = "--strict" in sys.argv[1:]
    failures = 0
    checked = 0
    for path in tracked_files():
        if path.suffix.lower() not in (".yml", ".yaml", ".json", ".jsonl"):
            continue
        checked += 1
        try:
            check_parse(path)
        except Exception as exc:
            failures += 1
            print(f"{path}: does not parse: {exc}")
            continue
        if path.parent == FORM_DIR:
            for error in check_form(path):
                failures += 1
                print(f"{path}: {error}")
    warnings = taxonomy_warnings()
    for warning in warnings:
        print(f"warning: {warning}")
    if strict:
        failures += len(warnings)
    if failures:
        print(f"validate: {failures} problem(s) in {checked} file(s)", file=sys.stderr)
        return 1
    print(f"validate: {checked} YAML/JSON file(s) OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
