from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def schema_path(root: Path | None = None) -> Path:
    candidates = []
    if root is not None:
        candidates.append(root / "schemas" / "ledger.schema.json")
    candidates.append(Path(__file__).resolve().parents[2] / "schemas" / "ledger.schema.json")
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError("schemas/ledger.schema.json not found")


def load_schema(root: Path | None = None) -> dict[str, Any]:
    return json.loads(schema_path(root).read_text())


def _type_ok(value: Any, t: str) -> bool:
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, TYPES[t])


def validate(value: Any, schema: dict[str, Any], root: dict[str, Any], path: str = "$") -> list[str]:
    if "$ref" in schema:
        target: Any = root
        for part in schema["$ref"].lstrip("#/").split("/"):
            target = target[part]
        return validate(value, target, root, path)
    errors: list[str] = []
    if "anyOf" in schema:
        if all(validate(value, s, root, path) for s in schema["anyOf"]):
            errors.append(f"{path}: matches no allowed shape")
        return errors
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(value, t) for t in types):
            return [f"{path}: expected {'/'.join(types)}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: not one of {schema['enum']}")
    if isinstance(value, str) and "pattern" in schema and not re.search(schema["pattern"], value):
        errors.append(f"{path}: does not match {schema['pattern']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: above {schema['maximum']}")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing {key}")
        props = schema.get("properties", {})
        for key, sub in props.items():
            if key in value:
                errors += validate(value[key], sub, root, f"{path}.{key}")
        extra = schema.get("additionalProperties", True)
        for key in value:
            if key in props:
                continue
            if extra is False:
                errors.append(f"{path}: unexpected {key}")
            elif isinstance(extra, dict):
                errors += validate(value[key], extra, root, f"{path}.{key}")
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for i, item in enumerate(value):
            errors += validate(item, schema["items"], root, f"{path}[{i}]")
    return errors


def validate_run(record: Any, schema: dict[str, Any]) -> list[str]:
    return validate(record, schema["$defs"]["run"], schema)


def validate_agent(entry: Any, schema: dict[str, Any]) -> list[str]:
    return validate(entry, schema["$defs"]["agent"], schema)


def validate_paths(paths: list[Path], schema: dict[str, Any]) -> list[str]:
    problems = []
    for path in paths:
        if path.is_dir():
            files = sorted(path.glob("*/run.json")) + sorted(path.glob("run.json")) + sorted(path.glob("agents.jsonl"))
        else:
            files = [path]
        for f in files:
            if f.name == "agents.jsonl":
                for n, line in enumerate(f.read_text().splitlines(), 1):
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        problems.append(f"{f}:{n}: not JSON")
                        continue
                    problems += [f"{f}:{n}: {e}" for e in validate_agent(entry, schema)]
            else:
                try:
                    record = json.loads(f.read_text())
                except (OSError, json.JSONDecodeError):
                    problems.append(f"{f}: not JSON")
                    continue
                problems += [f"{f}: {e}" for e in validate_run(record, schema)]
    return problems
