"""Tag audits: the machinery behind docs/protocol.md section 7.

A tag may appear in a published count only if it has passed an audit recorded in ledger/audits.jsonl.
Nothing here calls a model or spends money; a person reviews the runs and records each verdict.

Sampling algorithm. The candidates of a group are the clean runs of runs/index.jsonl (not confounded by an
invalidating incident): for the tagged group, runs that carry the tag; for the untagged group, runs that do not
carry it but sit in a cell (task, model, variant) where it occurs. Each candidate gets the key
sha256("<seed>:<tag>:<group>:<run id>"); candidates are sorted by key and the first N are taken, with N = 10
(20 for the claim classifier) or all of them when there are fewer. The same seed and the same index always give the
same list, and no random number generator is involved.

Fingerprint. See `fingerprint`: a sha256 over the detector's source, the source of every blackbox function it calls,
the patterns and constants it reads, the Context/Stream members it uses and the tag's taxonomy entry.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import re
import types
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

from blackbox import behaviours, schema, stream, taxonomy

CLASSIFIER = "claim-classifier"
TAGGED_SAMPLE = 10
UNTAGGED_SAMPLE = 10
CLASSIFIER_SAMPLE = 20
VERDICTS = ("correct", "wrong", "unclear")
GROUPS = ("tagged", "untagged")
PASSED, FAILED, UNAUDITED = "passed", "failed", "unaudited"
FIELDS = ("audit_id", "tag", "group", "seed", "task", "model", "run_id", "verdict", "reviewer", "date", "note",
          "detector_fingerprint")
AUDITS = Path("ledger") / "audits.jsonl"
SCHEMA = Path("schemas") / "audit.schema.json"
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class AuditError(ValueError):
    """A line or request that cannot be accepted."""


# ----------------------------------------------------------------------------- data

def load_index(root: Path) -> list[dict[str, Any]]:
    path = root / "runs" / "index.jsonl"
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("run_id"):
                rows.append(row)
    return rows


def load_audits(root: Path) -> list[dict[str, Any]]:
    path = root / AUDITS
    if not path.is_file():
        return []
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                out.append(row)
    return out


def _taxonomy_path(root: Path) -> Path:
    return root / "behaviour" / "taxonomy.yaml"


def known_tags(root: Path) -> list[str]:
    return list(taxonomy.load(_taxonomy_path(root))) + [CLASSIFIER]


def _clean(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if not r.get("confounded_by")]


def _cell(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("task_id")), str(row.get("model")), str(row.get("variant")))


def _has_tag(row: dict[str, Any], tag: str) -> bool:
    return tag in (row.get("behaviours") or [])


def _classifier_eligible(row: dict[str, Any]) -> bool:
    return row.get("claim_outcome") not in (None, "unknown")


def population(rows: list[dict[str, Any]], tag: str, group: str) -> list[dict[str, Any]]:
    """Every clean run that may be reviewed for this tag and group, sorted by run id."""
    clean = _clean(rows)
    if tag == CLASSIFIER:
        found = [r for r in clean if _classifier_eligible(r)] if group == "tagged" else []
    elif group == "tagged":
        found = [r for r in clean if _has_tag(r, tag)]
    else:
        cells = {_cell(r) for r in clean if _has_tag(r, tag)}
        found = [r for r in clean if not _has_tag(r, tag) and _cell(r) in cells]
    return sorted(found, key=lambda r: str(r["run_id"]))


def sample_size(tag: str, group: str) -> int:
    if tag == CLASSIFIER:
        return CLASSIFIER_SAMPLE if group == "tagged" else 0
    return TAGGED_SAMPLE if group == "tagged" else UNTAGGED_SAMPLE


def draw(candidates: list[dict[str, Any]], seed: int, tag: str, group: str, size: int) -> list[dict[str, Any]]:
    def key(row: dict[str, Any]) -> tuple[str, str]:
        digest = hashlib.sha256(f"{seed}:{tag}:{group}:{row['run_id']}".encode()).hexdigest()
        return digest, str(row["run_id"])
    return sorted(candidates, key=key)[:size]


def sample(rows: list[dict[str, Any]], tag: str, seed: int) -> dict[str, list[dict[str, Any]]]:
    """The runs to review for `tag` under `seed`, by group. Deterministic; reads nothing but `rows`."""
    out = {}
    for group in GROUPS:
        out[group] = draw(population(rows, tag, group), seed, tag, group, sample_size(tag, group))
    return out


# ----------------------------------------------------------------------------- fingerprint

def _members() -> dict[str, Any]:
    table: dict[str, Any] = {}
    for cls in (behaviours.Context, stream.Stream, stream.ToolUse, stream.ToolResult, stream.Texts):
        for name, value in vars(cls).items():
            if isinstance(value, property):
                value = value.fget
            if isinstance(value, types.FunctionType):
                table.setdefault(name, value)
    return table


def _walk_code(code: types.CodeType):
    yield code
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            yield from _walk_code(const)


def _is_ours(obj: Any) -> bool:
    return str(getattr(obj, "__module__", "")).startswith("blackbox")


def _collect(fn: Callable[..., Any], parts: dict[str, str], members: dict[str, Any]) -> None:
    label = f"{fn.__module__}.{fn.__qualname__}"
    if label in parts:
        return
    try:
        parts[label] = inspect.getsource(fn)
    except (OSError, TypeError):
        parts[label] = repr(fn.__code__.co_code) + repr(fn.__code__.co_consts)
    scope = fn.__globals__
    names = {n for code in _walk_code(fn.__code__) for n in code.co_names}
    modules = [v for n, v in scope.items() if n in names and isinstance(v, types.ModuleType)
               and v.__name__.startswith("blackbox")]
    for name in sorted(names):
        value = scope.get(name)
        if isinstance(value, re.Pattern):
            parts[f"{fn.__module__}.{name}"] = f"{value.pattern!r} {value.flags}"
        elif isinstance(value, (str, int, float, bool, bytes)):
            parts[f"{fn.__module__}.{name}"] = repr(value)
        elif isinstance(value, (set, frozenset)):
            parts[f"{fn.__module__}.{name}"] = repr(sorted(map(repr, value)))
        elif isinstance(value, (tuple, list)):
            parts[f"{fn.__module__}.{name}"] = repr(value)
        elif isinstance(value, dict):
            parts[f"{fn.__module__}.{name}"] = repr(sorted((repr(k), repr(v)) for k, v in value.items()))
        elif isinstance(value, types.FunctionType) and _is_ours(value):
            _collect(value, parts, members)
        for mod in modules:
            attr = getattr(mod, name, None)
            if isinstance(attr, types.FunctionType) and _is_ours(attr):
                _collect(attr, parts, members)
        member = members.get(name)
        if member is not None and _is_ours(member):
            _collect(member, parts, members)


def taxonomy_entry(root: Path, tag: str) -> Any:
    path = _taxonomy_path(root)
    entry: Any = None
    if path.is_file():
        import yaml

        def find(node: Any) -> Any:
            if isinstance(node, dict):
                if node.get("id") == tag:
                    return node
                for value in node.values():
                    hit = find(value)
                    if hit is not None:
                        return hit
            elif isinstance(node, list):
                for item in node:
                    hit = find(item)
                    if hit is not None:
                        return hit
            return None
        entry = find(yaml.safe_load(path.read_text()) or {})
    if entry is None:
        entry = {"id": tag, "polarity": taxonomy.load(path).get(tag, "unknown")}
    return entry


def fingerprint(tag: str, root: Path) -> str:
    """Stable sha256 of a tag's detector code and taxonomy entry.

    Detector: the registered function's source (decorator included, so id, confidence and `needs` count), plus the
    source of every blackbox function it reaches by name, the value of every module-level pattern or constant it
    reads, and the source of every Context, Stream and tool-event member it uses. Taxonomy: the tag's entry in
    behaviour/taxonomy.yaml as canonical JSON. A tag with no detector hashes the entry and the word `undetected`.
    The claim classifier hashes `report.claim_outcome` and everything it reaches (claims.py, the stream parser).
    Any edit to any of these changes the hash, which makes the tag unaudited until it is audited again.
    """
    members = _members()
    parts: dict[str, str] = {}
    if tag == CLASSIFIER:
        from blackbox import report
        _collect(report.claim_outcome, parts, members)
        parts["outcomes"] = repr(report.OUTCOMES)
    else:
        det = behaviours.REGISTRY.get(tag)
        if det is None:
            parts["detector"] = "undetected"
        else:
            parts["confidence"] = det.confidence
            parts["needs"] = repr(det.needs)
            _collect(det.fn, parts, members)
        parts["taxonomy"] = json.dumps(taxonomy_entry(root, tag), sort_keys=True, default=str)
    blob = json.dumps(sorted(parts.items()), ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


# ----------------------------------------------------------------------------- validation

def load_schema(root: Path) -> dict[str, Any]:
    for base in (root, Path(__file__).resolve().parents[2]):
        if (base / SCHEMA).is_file():
            return json.loads((base / SCHEMA).read_text())
    raise FileNotFoundError(str(SCHEMA))


def check_line(line: dict[str, Any], root: Path, rows: list[dict[str, Any]], tags: list[str] | None = None) -> list[str]:
    """Every reason this line is nonsense. Empty when it is acceptable."""
    problems = schema.validate(line, load_schema(root), load_schema(root))
    if problems:
        return problems
    tag, group, run_id = line["tag"], line["group"], line["run_id"]
    if tag not in (tags if tags is not None else known_tags(root)):
        problems.append(f"tag {tag!r} is not in the taxonomy")
    row = next((r for r in rows if r["run_id"] == run_id), None)
    if row is None:
        return problems + [f"run {run_id} is not in runs/index.jsonl"]
    if (line["task"], line["model"]) != (row.get("task_id"), row.get("model")):
        problems.append(f"task/model do not match the index for {run_id}: {row.get('task_id')} / {row.get('model')}")
    if row.get("confounded_by"):
        problems.append(f"run {run_id} is confounded by {', '.join(row['confounded_by'])} and is not audited")
    if tag == CLASSIFIER:
        if group != "tagged":
            problems.append("the claim classifier audit has only tagged-group lines")
        elif not _classifier_eligible(row):
            problems.append(f"run {run_id} has no recorded claim outcome")
    elif group == "tagged" and not _has_tag(row, tag):
        problems.append(f"run {run_id} does not carry the tag {tag}")
    elif group == "untagged":
        if _has_tag(row, tag):
            problems.append(f"run {run_id} carries the tag {tag}, so it cannot be in the untagged group")
        elif _cell(row) not in {_cell(r) for r in rows if _has_tag(r, tag)}:
            problems.append(f"run {run_id} is in a cell (task, model, variant) where {tag} never occurs")
    return problems


def check_ledger(root: Path) -> list[str]:
    """Problems with ledger/audits.jsonl as a whole: shape, index membership and duplicates."""
    path = root / AUDITS
    if not path.is_file():
        return []
    rows = load_index(root)
    tags = known_tags(root)
    problems, seen = [], set()
    for n, text in enumerate(path.read_text().splitlines(), 1):
        if not text.strip():
            continue
        try:
            line = json.loads(text)
        except json.JSONDecodeError:
            problems.append(f"{path}:{n}: not JSON")
            continue
        if not isinstance(line, dict):
            problems.append(f"{path}:{n}: expected an object")
            continue
        found = check_line(line, root, rows, tags)
        problems += [f"{path}:{n}: {p}" for p in found]
        key = (line.get("audit_id"), line.get("group"), line.get("run_id"))
        if not found and key in seen:
            problems.append(f"{path}:{n}: run {line.get('run_id')} is already recorded in audit {line.get('audit_id')}")
        seen.add(key)
    return problems


def make_line(root: Path, tag: str, group: str, seed: int, run_id: str, verdict: str, reviewer: str,
              on: str, note: str, audit_id: str | None = None) -> dict[str, Any]:
    """Build a validated line, or raise AuditError. Task and model come from the index, the fingerprint from the code."""
    rows = load_index(root)
    row = next((r for r in rows if r["run_id"] == run_id), None)
    if row is None:
        raise AuditError(f"run {run_id} is not in runs/index.jsonl")
    fp = fingerprint(tag, root)
    line = {"audit_id": audit_id or f"{tag}-seed{seed}-{fp[:8]}", "tag": tag, "group": group, "seed": seed,
            "task": row.get("task_id"), "model": row.get("model"), "run_id": run_id, "verdict": verdict,
            "reviewer": reviewer, "date": on, "note": note, "detector_fingerprint": fp}
    problems = check_line(line, root, rows)
    if not problems and tag in known_tags(root):
        listed = {r["run_id"] for r in sample(rows, tag, seed)[group]}
        if run_id not in listed:
            problems.append(f"run {run_id} is not in the {group} sample for tag {tag} and seed {seed}")
        for other in load_audits(root):
            if other.get("audit_id") == line["audit_id"]:
                if other.get("run_id") == run_id and other.get("group") == group:
                    problems.append(f"run {run_id} is already recorded in audit {line['audit_id']}")
                if (other.get("tag"), other.get("seed"), other.get("detector_fingerprint")) != (tag, seed, fp):
                    problems.append(f"audit {line['audit_id']} was started with another tag, seed or detector fingerprint")
                    break
    if problems:
        raise AuditError("; ".join(problems))
    return line


def record(root: Path, **kwargs: Any) -> dict[str, Any]:
    line = make_line(root, **kwargs)
    path = root / AUDITS
    path.parent.mkdir(parents=True, exist_ok=True)
    needs_newline = path.is_file() and path.stat().st_size > 0 and not path.read_text().endswith("\n")
    with path.open("a") as fh:
        fh.write(("\n" if needs_newline else "") + json.dumps(line, ensure_ascii=False) + "\n")
    return line


# ----------------------------------------------------------------------------- status

@dataclass
class Status:
    tag: str
    state: str = UNAUDITED
    reason: str = "no audit recorded"
    audit_id: str | None = None
    counts: dict[str, int] = field(default_factory=dict)


def _tally(lines: list[dict[str, Any]], group: str) -> dict[str, int]:
    latest: dict[str, str] = {}
    for line in lines:
        if line.get("group") == group:
            latest[str(line.get("run_id"))] = str(line.get("verdict"))
    return {v: sum(1 for x in latest.values() if x == v) for v in VERDICTS}


def tag_status(tag: str, rows: list[dict[str, Any]], audits: list[dict[str, Any]], current: str) -> Status:
    """passed, failed or unaudited for one tag, given the index rows, the audit lines and the current fingerprint."""
    mine = [a for a in audits if a.get("tag") == tag]
    status = Status(tag)
    if not mine:
        return status
    valid = [a for a in mine if a.get("detector_fingerprint") == current]
    if not valid:
        status.reason = "detector or taxonomy entry changed since the last audit"
        return status
    audit_id = str(valid[-1].get("audit_id"))
    lines = [a for a in valid if a.get("audit_id") == audit_id]
    status.audit_id = audit_id
    if len({a.get("seed") for a in lines}) != 1:
        status.reason = "lines of one audit disagree on the seed"
        return status
    need = {g: min(sample_size(tag, g), len(population(rows, tag, g))) for g in GROUPS}
    tagged, untagged = _tally(lines, "tagged"), _tally(lines, "untagged")
    status.counts = {"tagged_correct": tagged["correct"], "tagged_wrong": tagged["wrong"], "tagged_unclear": tagged["unclear"],
                     "tagged_needed": need["tagged"], "untagged_correct": untagged["correct"],
                     "untagged_wrong": untagged["wrong"], "untagged_unclear": untagged["unclear"],
                     "untagged_needed": need["untagged"]}
    if need["tagged"] == 0:
        status.reason = "no run carries this tag"
        return status
    decided_t = tagged["correct"] + tagged["wrong"]
    decided_u = untagged["correct"] + untagged["wrong"]
    if decided_t < need["tagged"] or decided_u < need["untagged"]:
        status.reason = (f"incomplete: {decided_t} of {need['tagged']} tagged and {decided_u} of {need['untagged']} "
                         f"untagged runs decided")
        return status
    need_correct = need["tagged"] - need["tagged"] // 10
    allowed_missed = need["untagged"] // 10
    ok_t = tagged["correct"] >= need_correct
    ok_u = untagged["wrong"] <= allowed_missed
    status.state = PASSED if ok_t and ok_u else FAILED
    if status.state == PASSED:
        status.reason = "audit passed"
    else:
        why = []
        if not ok_t:
            why.append(f"{tagged['correct']} of {need['tagged']} tagged runs correct, {need_correct} needed")
        if not ok_u:
            why.append(f"{untagged['wrong']} untagged runs show the behaviour, {allowed_missed} allowed")
        status.reason = "; ".join(why)
    return status


def statuses(root: Path, rows: list[dict[str, Any]] | None = None) -> dict[str, Status]:
    rows = load_index(root) if rows is None else rows
    audits = load_audits(root)
    return {tag: tag_status(tag, rows, audits, fingerprint(tag, root)) for tag in known_tags(root)}


def states(root: Path) -> dict[str, str]:
    return {tag: s.state for tag, s in statuses(root).items()}
