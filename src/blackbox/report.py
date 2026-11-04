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
        "task_version": r.get("task_version") or 1, "protocol_version": r.get("protocol_version"), "phase": r.get("phase"),
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
    """A run made under a protocol version in a phase (both stamps present). Anything else, including a run stamped with a
    protocol version but no phase, is exploratory."""
    return f"protocol {row['protocol_version']}" if row.get("protocol_version") and row.get("phase") else "exploratory"


def _model(row: dict[str, Any]) -> str:
    return str(row.get("model") or "unknown")


def _passed(states: dict[str, str] | None, tag: str) -> bool:
    return (states or {}).get(tag) == "passed"


def _claims_audited(states: dict[str, str] | None) -> bool:
    """Every figure that comes from the claim classifier is shown only while its audit has passed."""
    return _passed(states, audit.CLASSIFIER)


UNAUDITED = "unaudited"


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
        "the last column counts only runs where a result check contradicted what the agent said. Both come from the claim classifier "
        f"and show \"{UNAUDITED}\", with no count, until the classifier audit (`{audit.CLASSIFIER}`) has passed; the last column also needs the tag "
        f"{CONTRADICTED} to have passed its own audit (docs/protocol.md section 7). Pass rate and cost do not depend on either.",
        "",
        "| Model | Variant | Basis | Clean runs | Pass rate | Mean cost (USD) | Claimed success, failed grader | Of those, claim contradicted by a result check |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for (model, variant, basis), clean in sorted(cells.items()):
        passes = sum(1 for r in clean if r.get("passed"))
        overclaims: Any = sum(1 for r in clean if r.get("claim_outcome") == "claimed-failed")
        contradicted: Any = sum(1 for r in clean if r.get("claim_outcome") == "claimed-failed" and CONTRADICTED in (r.get("behaviours") or []))
        if not _claims_audited(states):
            overclaims = UNAUDITED
        if not (_claims_audited(states) and _passed(states, CONTRADICTED)):
            contradicted = UNAUDITED
        lines.append(f"| {_cell(model)} | {_cell(variant)} | {basis} | {len(clean)} | {passes}/{len(clean)} ({100 * passes / len(clean):.0f}%) | "
                     f"{_fmt(_mean([r.get('cost_usd') for r in clean]), '{:.4f}')} | {overclaims} | {contradicted} |")
    if not cells:
        lines.append("| none | | | 0 | | | | |")
    lines.append("")
    return lines


def _groups(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str, str], list[dict[str, Any]]]:
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row.get("task_id")), _version(row), _model(row), str(row.get("variant")))].append(row)
    return groups


DETAIL_FILE = "results-detail.md"


def _clean(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if not r.get("confounded_by")]


def _pct(passed: int, total: int) -> str:
    return f"{passed}/{total} ({100 * passed / total:.0f}%)" if total else "n/a"


def _model_cell(clean: list[dict[str, Any]]) -> str:
    """Pass rate, mean cost and mean turns of one model's clean runs, in one short cell."""
    if not clean:
        return "-"
    cost, turns = _mean([r.get("cost_usd") for r in clean]), _mean([r.get("turns") for r in clean])
    return (f"{_pct(sum(1 for r in clean if r.get('passed')), len(clean))}, "
            f"{_fmt(cost, '${:.3f}')}, {_fmt(turns, '{:.1f}')} turns")


def _plain(rows: list[dict[str, Any]], states: dict[str, str] | None) -> list[str]:
    """The plain-language top of the page. Every figure is computed from `rows` and `states`."""
    clean = _clean(rows)
    tasks = sorted({str(r.get("task_id")) for r in clean})
    models = sorted({_model(r) for r in clean})
    by_task: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in clean:
        by_task[(str(r.get("task_id")), _version(r))].append(r)
    always = sum(1 for g in by_task.values() if all(r.get("passed") for r in g))
    tags = sorted({b for r in clean for b in r.get("behaviours") or []})
    audited = [t for t in tags if _passed(states, t)]
    lines = [
        "## In plain words",
        "",
        "An AI coding agent is given a small programming job in a sandbox. Afterwards a hidden checker, which the agent never "
        "sees, decides whether the job was really done. Everything the agent did is recorded, so any claim on this page can be "
        "traced to a run you can open.",
        "",
        f"- **What was run:** {len(rows)} runs of {len(tasks)} tasks (named below) by {len(models)} model"
        f"{'' if len(models) == 1 else 's'} ({', '.join(models) or 'none'}). {len(clean)} are clean and counted; "
        f"{len(rows) - len(clean)} were set aside because a logged mistake of ours could have affected them.",
        f"- **Pass rate:** the hidden checker passed {sum(1 for r in clean if r.get('passed'))} of {len(clean)} clean runs overall; "
        "the tables below split it by model and by task, because pooling models would hide differences.",
        f"- **How hard the tasks were:** {always} of {len(by_task)} task versions were passed in every clean run. "
        "When nearly everything passes, the runs cannot tell the models apart, so a small gap between models here is not evidence "
        "that one is better.",
        f"- **Behaviour tags are leads, not findings:** {len(tags)} different tags appear on clean runs and {len(audited)} "
        f"{'has' if len(audited) == 1 else 'have'} passed an audit. A tag is counted only after it is audited by a person "
        "reading sample runs; the rest read \"unaudited\" and carry no number.",
        f"- **Claim figures:** how often an agent said it succeeded when the checker disagreed comes from a classifier whose audit has "
        f"{'passed, so the counts are shown' if _claims_audited(states) else 'not yet passed, so those counts are withheld and show unaudited'}.",
        "",
        "### Per model",
        "",
        "Clean runs only. Pass rate, mean cost per run and mean turns (steps the agent took). Models are never pooled.",
        "",
        "| Model | Variant | Basis | Clean runs | Pass rate | Mean cost (USD) | Mean turns |",
        "|---|---|---|---|---|---|---|",
    ]
    cells: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in clean:
        cells[(_model(r), str(r.get("variant")), _basis(r))].append(r)
    for (model, variant, basis), g in sorted(cells.items()):
        lines.append(f"| {_cell(model)} | {_cell(variant)} | {basis} | {len(g)} | {_pct(sum(1 for r in g if r.get('passed')), len(g))} | "
                     f"{_fmt(_mean([r.get('cost_usd') for r in g]), '{:.4f}')} | {_fmt(_mean([r.get('turns') for r in g]), '{:.1f}')} |")
    if not cells:
        lines.append("| none | | | 0 | | | |")
    lines += [
        "",
        "### Per task",
        "",
        "One row per task version, one column per model, each cell showing pass rate, mean cost per run and mean turns. "
        "Variants and bases are pooled here; the full split is in the "
        f"[detailed results]({DETAIL_FILE}).",
        "",
        "| Task | Version | " + " | ".join(_cell(m) for m in models) + " |" if models else "| Task | Version |",
        "|---|---|" + "---|" * len(models),
    ]
    for (task, version), g in sorted(by_task.items()):
        lines.append(f"| {_cell(task)} | v{version} | " + " | ".join(_model_cell([r for r in g if _model(r) == m]) for m in models) + " |")
    if not by_task:
        lines.append("| none | | |")
    lines += [
        "",
        "### What these numbers can and cannot tell you",
        "",
        "- They show what happened in these runs. They are not a ranking of the models.",
        "- Groups are small and many tasks were passed every time, so these runs say little about differences between models or "
        "between the bare and plumbed variants.",
        "- Runs marked exploratory were made before the written evaluation protocol and support no conclusion.",
        "- A tag marked unaudited is a lead worth reading the run for. It is not a finding.",
        "",
        "### Glossary",
        "",
        "- **Run:** one agent attempting one task once. Every run is recorded and can be replayed.",
        "- **Task:** a small programming job with a trap, such as a hidden instruction or an impossible requirement.",
        "- **Grader:** the hidden checker that decides pass or fail. The agent never sees it.",
        "- **Variant:** bare means the agent had no extra setup; plumbed means it also had instruction files, permissions and hooks.",
        "- **Tag:** a label such as minimal-diff or test-tampering that a detector puts on a run to describe a behaviour.",
        "- **Audit:** a person reads a sample of runs carrying a tag and records whether the tag was right. See docs/protocol.md section 7.",
        "- **Unaudited:** the tag or figure has not passed an audit, so no count is shown.",
        "- **Claim classifier:** the detector that reads the agent's final message and decides whether it claimed success or "
        "said something was unmet. Its figures are shown only after it passes an audit.",
        "- **Exploratory vs protocol:** exploratory runs predate the written evaluation protocol (docs/protocol.md) and show what "
        "happened without supporting a conclusion; protocol runs follow its frozen tasks and rules.",
        "- **Clean vs confounded:** a confounded run is one a logged incident says may be unreliable; it is excluded from every rate.",
        "",
    ]
    return lines


def render(rows: list[dict[str, Any]], incidents: list[dict[str, Any]] | None = None,
           states: dict[str, str] | None = None) -> str:
    """The whole report as one text: the short page followed by the detail page."""
    return render_main(rows, incidents, states) + "\n" + render_detail(rows, incidents, states)


def render_main(rows: list[dict[str, Any]], incidents: list[dict[str, Any]] | None = None,
                states: dict[str, str] | None = None) -> str:
    """The short page, docs/results.md. `states` maps a tag to its audit state; a tag missing from it is unaudited."""
    confounded = [r for r in rows if r.get("confounded_by")]
    lines = [
        "# Results",
        "",
        "Generated by `python -m blackbox report` from `runs/index.jsonl` and `ledger/incidents.jsonl`. Do not edit by hand.",
        "",
        f"Runs: {len(rows)}. Clean: {len(rows) - len(confounded)}. Confounded: {len(confounded)}. "
        f"Per task, variant and tag detail, the claims table and the confounded runs are in [{DETAIL_FILE}]({DETAIL_FILE}).",
        "",
    ]
    lines += _plain(rows, states)
    lines += _by_model(rows, states)
    return "\n".join(lines)


def render_detail(rows: list[dict[str, Any]], incidents: list[dict[str, Any]] | None = None,
                  states: dict[str, str] | None = None) -> str:
    titles = {str(i.get("id")): str(i.get("title", "")) for i in incidents or []}
    groups = _groups(rows)
    confounded = [r for r in rows if r.get("confounded_by")]
    clean_total = len(rows) - len(confounded)
    lines = [
        "# Detailed results",
        "",
        "Generated by `python -m blackbox report`. Do not edit by hand. The short page is [results.md](results.md).",
        "",
        f"Runs: {len(rows)}. Clean: {clean_total}. Confounded: {len(confounded)}.",
        "",
        "Pass rates, means and behaviour counts use clean runs only. A run is confounded when an incident with "
        "`invalidates_results: true` lists it; those runs are listed under \"Confounded runs\" below.",
        "",
    ]
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
        "No claim: neither. "
        f"The classification is the claim classifier's (`{audit.CLASSIFIER}`); its columns show \"{UNAUDITED}\", with no count, "
        "until its audit has passed (docs/protocol.md section 7).",
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
        figures = [c["claimed-passed"], c["claimed-failed"], unmet_pass, unmet_fail, other]
        shown = figures if _claims_audited(states) else [UNAUDITED] * len(figures)
        lines.append(f"| {_cell(task)} | v{version} | {_cell(model)} | {_cell(variant)} | {len(clean)} | " + " | ".join(map(str, shown)) + " |")
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
    incidents, states = load_incidents(root), audit.states(root)
    (out.parent / DETAIL_FILE).write_text(redactor.text(render_detail(rows, incidents, states)))
    out.write_text(redactor.text(render_main(rows, incidents, states)))
    return out
