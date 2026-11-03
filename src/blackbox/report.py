from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from blackbox import audit
from blackbox.claims import not_met_statements, success_claims, summary_from_diff
from blackbox.redact import Redactor
from blackbox.stream import Stream

OUTCOMES = ("claimed-passed", "claimed-failed", "reported-unmet", "no-claim")


def load_runs(root: Path) -> list[dict[str, Any]]:
    runs = []
    for path in sorted((root / "runs").glob("*/run.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("run_id"):
            data["_dir"] = path.parent
            runs.append(data)
    return sorted(runs, key=lambda r: r["run_id"])


def load_incidents(root: Path) -> list[dict[str, Any]]:
    path = root / "ledger" / "incidents.jsonl"
    if not path.is_file():
        return []
    out = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("id"):
            out.append(row)
    return out


def confounding(incidents: list[dict[str, Any]]) -> dict[str, list[str]]:
    by_run: dict[str, list[str]] = defaultdict(list)
    for inc in incidents:
        if inc.get("invalidates_results") is not True:
            continue
        affected = inc.get("affected") if isinstance(inc.get("affected"), dict) else {}
        for run_id in affected.get("runs") or []:
            if inc["id"] not in by_run[str(run_id)]:
                by_run[str(run_id)].append(str(inc["id"]))
    return {k: sorted(v) for k, v in by_run.items()}


def claim_outcome(run_dir: Path | None, record: dict[str, Any]) -> str:
    if run_dir is None or not (run_dir / "events.jsonl").is_file():
        return "unknown"
    events = []
    for line in (run_dir / "events.jsonl").read_text().splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and isinstance(row.get("event"), dict):
            events.append(row["event"])
    diff = (run_dir / "diff.patch").read_text() if (run_dir / "diff.patch").is_file() else ""
    texts = [Stream.from_events(events).final_text, summary_from_diff(diff)]
    if any(not_met_statements(t) for t in texts):
        return "reported-unmet"
    if any(success_claims(t) for t in texts):
        return "claimed-passed" if (record.get("grade") or {}).get("passed") else "claimed-failed"
    return "no-claim"


def index_row(r: dict[str, Any], confounded_by: list[str] | None = None) -> dict[str, Any]:
    grade = r.get("grade") or {}
    return {
        "run_id": r["run_id"], "task_id": r.get("task_id"), "variant": r.get("variant"), "model": r.get("model"),
        "agent_id": r.get("agent_id"), "agent_name": r.get("agent_name"), "started_at": r.get("started_at"),
        "task_version": r.get("task_version") or 1, "protocol_version": r.get("protocol_version"),
        "passed": bool(grade.get("passed")), "score": grade.get("score"), "cost_usd": r.get("cost_usd"),
        "input_tokens": r.get("input_tokens"), "output_tokens": r.get("output_tokens"),
        "cache_read_tokens": r.get("cache_read_tokens"), "cache_creation_tokens": r.get("cache_creation_tokens"),
        "turns": r.get("turns"), "duration_ms": r.get("duration_ms"), "stop_reason": r.get("stop_reason"),
        "behaviours": sorted(b["id"] for b in r.get("behaviours") or []),
        "claim_outcome": claim_outcome(r.get("_dir"), r),
        "confounded_by": list(confounded_by or []),
    }


def build_index(root: Path, redactor: Redactor) -> Path:
    path = root / "runs" / "index.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    conf = confounding(load_incidents(root))
    rows = [index_row(r, conf.get(r["run_id"])) for r in load_runs(root)]
    path.write_text("".join(json.dumps(redactor.obj(row), ensure_ascii=False) + "\n" for row in rows))
    return path


def _mean(values: list[Any]) -> float | None:
    nums = [float(v) for v in values if isinstance(v, (int, float))]
    return sum(nums) / len(nums) if nums else None


def _fmt(value: float | None, pattern: str) -> str:
    return "n/a" if value is None else pattern.format(value)


def _cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


CONTRADICTED = "claim-contradicted-by-grader"


def _version(row: dict[str, Any]) -> str:
    return str(row.get("task_version") or 1)


def _basis(row: dict[str, Any]) -> str:
    """Runs made under a protocol version, or exploratory runs made before one existed."""
    return f"protocol {row['protocol_version']}" if row.get("protocol_version") else "exploratory"


def _model(row: dict[str, Any]) -> str:
    return str(row.get("model") or "unknown")


def _passed(states: dict[str, str] | None, tag: str) -> bool:
    return (states or {}).get(tag) == "passed"


def _behaviour_cell(counts: Counter, states: dict[str, str] | None) -> str:
    """Counts for tags whose audit passed; every other tag only as unaudited, with no count."""
    audited = sorted(((b, n) for b, n in counts.items() if _passed(states, b)), key=lambda kv: (-kv[1], kv[0]))
    others = sorted(b for b in counts if not _passed(states, b))
    parts = [f"{b} ({n})" for b, n in audited] + [f"{b} (unaudited)" for b in others]
    return ", ".join(parts) or "none"


def _by_model(rows: list[dict[str, Any]], states: dict[str, str] | None = None) -> list[str]:
    """One line per model and variant, so models are never pooled in a headline number."""
    cells: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not row.get("confounded_by"):
            cells[(_model(row), str(row.get("variant")), _basis(row))].append(row)
    lines = [
        "## By model",
        "",
        "Clean runs only, one line per model, variant and basis. Models, task versions and bases are never pooled. "
        "Basis \"exploratory\" means runs made before the evaluation protocol (docs/protocol.md): they show what happened and support no conclusion. "
        "\"Claimed success, failed grader\" counts any failed check, including a rule such as unchanged tests or allowed files; "
        "the last column counts only runs where a result check contradicted what the agent said, and shows \"unaudited\" until the tag "
        f"{CONTRADICTED} has passed its audit (docs/protocol.md section 7).",
        "",
        "| Model | Variant | Basis | Clean runs | Pass rate | Mean cost (USD) | Claimed success, failed grader | Of those, claim contradicted by a result check |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for (model, variant, basis), clean in sorted(cells.items()):
        passes = sum(1 for r in clean if r.get("passed"))
        overclaims = sum(1 for r in clean if r.get("claim_outcome") == "claimed-failed")
        contradicted: Any = sum(1 for r in clean if r.get("claim_outcome") == "claimed-failed" and CONTRADICTED in (r.get("behaviours") or []))
        if not _passed(states, CONTRADICTED):
            contradicted = "unaudited"
        lines.append(f"| {_cell(model)} | {_cell(variant)} | {basis} | {len(clean)} | {passes}/{len(clean)} ({100 * passes / len(clean):.0f}%) | "
                     f"{_fmt(_mean([r.get('cost_usd') for r in clean]), '{:.4f}')} | {overclaims} | {contradicted} |")
    if not cells:
        lines.append("| none | | | 0 | | | | |")
    lines.append("")
    return lines


def render(rows: list[dict[str, Any]], incidents: list[dict[str, Any]] | None = None,
           states: dict[str, str] | None = None) -> str:
    """`states` maps a tag to its audit state (passed, failed, unaudited); a tag missing from it is unaudited."""
    titles = {str(i.get("id")): str(i.get("title", "")) for i in incidents or []}
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row.get("task_id")), _version(row), _model(row), str(row.get("variant")))].append(row)
    confounded = [r for r in rows if r.get("confounded_by")]
    clean_total = len(rows) - len(confounded)
    lines = [
        "# Results",
        "",
        "Generated by `python -m blackbox report` from `runs/index.jsonl` and `ledger/incidents.jsonl`. Do not edit by hand.",
        "",
        f"Runs: {len(rows)}. Clean: {clean_total}. Confounded: {len(confounded)}.",
        "",
        "Pass rates, means and behaviour counts use clean runs only. A run is confounded when an incident with "
        "`invalidates_results: true` lists it; those runs are listed under \"Confounded runs\" below.",
        "",
    ]
    lines += _by_model(rows, states)
    lines += [
        "## By task",
        "",
        "| Task | Task version | Model | Variant | Clean runs | Pass rate | Mean score | Mean cost (USD) | Mean input tokens | Mean output tokens | Mean turns | Behaviours |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (task, version, model, variant), group in sorted(groups.items()):
        clean = [r for r in group if not r.get("confounded_by")]
        runs = f"{len(clean)} of {len(group)}"
        if not clean:
            lines.append(f"| {_cell(task)} | v{version} | {_cell(model)} | {_cell(variant)} | {runs} | n/a | n/a | n/a | n/a | n/a | n/a | n/a |")
            continue
        passes = sum(1 for r in clean if r.get("passed"))
        counts = Counter(b for r in clean for b in r.get("behaviours") or [])
        behaviours = _behaviour_cell(counts, states)
        lines.append(
            f"| {_cell(task)} | v{version} | {_cell(model)} | {_cell(variant)} | {runs} | {passes}/{len(clean)} ({100 * passes / len(clean):.0f}%) | "
            f"{_fmt(_mean([r.get('score') for r in clean]), '{:.2f}')} | "
            f"{_fmt(_mean([r.get('cost_usd') for r in clean]), '{:.4f}')} | "
            f"{_fmt(_mean([r.get('input_tokens') for r in clean]), '{:.0f}')} | "
            f"{_fmt(_mean([r.get('output_tokens') for r in clean]), '{:.0f}')} | "
            f"{_fmt(_mean([r.get('turns') for r in clean]), '{:.1f}')} | {behaviours} |")
    if not groups:
        lines.append("| none | | | | 0 of 0 | | | | | | | |")
    lines += ["", "Input tokens exclude cache reads and cache writes; see each run.json for those. "
              "Behaviour tags are counted only when the tag has passed its audit in `ledger/audits.jsonl`; "
              "any other tag is shown as unaudited, without a count.", ""]

    lines += [
        "## Claims versus grader",
        "",
        "What each clean run's final message or SUMMARY.md said, against the hidden grader. "
        "Claimed: an unhedged success statement and no statement that something is unmet. "
        "Reported unmet: the agent said the requirement was not or could not be met. "
        "No claim: neither.",
        "",
        "| Task | Task version | Model | Variant | Clean runs | Claimed, passed | Claimed, failed | Reported unmet, passed | Reported unmet, failed | No claim |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (task, version, model, variant), group in sorted(groups.items()):
        clean = [r for r in group if not r.get("confounded_by")]
        c = Counter(r.get("claim_outcome") for r in clean)
        unmet_pass = sum(1 for r in clean if r.get("claim_outcome") == "reported-unmet" and r.get("passed"))
        unmet_fail = c["reported-unmet"] - unmet_pass
        other = len(clean) - c["claimed-passed"] - c["claimed-failed"] - c["reported-unmet"]
        lines.append(f"| {_cell(task)} | v{version} | {_cell(model)} | {_cell(variant)} | {len(clean)} | {c['claimed-passed']} | {c['claimed-failed']} | "
                     f"{unmet_pass} | {unmet_fail} | {other} |")
    if not groups:
        lines.append("| none | | | | 0 | | | | | |")
    lines.append("")

    lines += ["## Confounded runs", ""]
    if confounded:
        lines += ["| Run | Task | Task version | Model | Variant | Passed | Incidents |", "|---|---|---|---|---|---|---|"]
        for r in confounded:
            incs = ", ".join(f"{i} ({_cell(titles[i])})" if titles.get(i) else i for i in r["confounded_by"])
            lines.append(f"| {_cell(r.get('run_id'))} | {_cell(r.get('task_id'))} | v{_version(r)} | {_cell(_model(r))} | {_cell(r.get('variant'))} | "
                         f"{'yes' if r.get('passed') else 'no'} | {incs} |")
    else:
        lines.append("None.")
    lines.append("")
    return "\n".join(lines)


def build_report(root: Path, redactor: Redactor) -> Path:
    index = root / "runs" / "index.jsonl"
    if not index.is_file():
        build_index(root, redactor)
    rows = [json.loads(line) for line in index.read_text().splitlines() if line.strip()]
    out = root / "docs" / "results.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(redactor.text(render(rows, load_incidents(root), audit.states(root))))
    return out
