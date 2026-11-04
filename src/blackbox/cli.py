from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from blackbox import audit, phase, reanalyse, report, schema, transcript
from blackbox.live import LiveView, resolve_run, watch
from blackbox.envfile import find_env_file, read_env_values
from blackbox.redact import Redactor, scan
from blackbox.runner import HarnessError, RunOptions, run


def _redactor(env_file: str | None) -> Redactor:
    path = find_env_file(env_file)
    return Redactor(read_env_values(path).values() if path else ())


def cmd_run(a: argparse.Namespace) -> int:
    if not a.task_dir and not a.task:
        print("blackbox: give TASK_DIR or --task ID", file=sys.stderr)
        return 2
    opts = RunOptions(
        task_dir=Path(a.task_dir) if a.task_dir else Path(a.root) / "tasks" / a.task, variant=a.variant, model=a.model, budget_usd=a.budget_usd,
        plumbing_dir=Path(a.plumbing_dir) if a.plumbing_dir else None, root=Path(a.root),
        env_file=a.env_file, agent_cli=a.agent_cli, timeout_seconds=a.timeout,
        keep_workspace=a.keep_workspace, taxonomy_path=Path(a.taxonomy) if a.taxonomy else None,
        sandbox=a.sandbox, view=LiveView() if a.live else None, phase=a.phase)
    try:
        run_dir = run(opts)
    except HarnessError as exc:
        print(f"blackbox: {exc}", file=sys.stderr)
        return 2
    print(run_dir)
    return 0


def cmd_watch(a: argparse.Namespace) -> int:
    try:
        run_dir = resolve_run(a.run, Path(a.root))
    except FileNotFoundError as exc:
        print(f"blackbox: {exc}", file=sys.stderr)
        return 2
    view = LiveView(color=False if a.no_color else None)
    try:
        return watch(run_dir, view, follow=not a.no_follow, timeout=a.timeout, replay=a.replay)
    except KeyboardInterrupt:
        return 130


def cmd_reanalyse(a: argparse.Namespace) -> int:
    root = Path(a.root)
    runs_dir = Path(a.runs) if a.runs else root / "runs"
    results = reanalyse.reanalyse(runs_dir, root, Path(a.taxonomy) if a.taxonomy else None, write=not a.dry_run)
    errors = 0
    for r in results:
        if "error" in r:
            errors += 1
            print(f"{r['run_id']}: error: {r['error']}")
            continue
        added = sorted(set(r["after"]) - set(r["before"]))
        removed = sorted(set(r["before"]) - set(r["after"]))
        change = ("updated" if not a.dry_run else "would update") if r["changed"] else "unchanged"
        detail = "".join([f"  +{x}" for x in added] + [f"  -{x}" for x in removed])
        print(f"{r['run_id']}: {change}{detail}")
    print(f"\n{len(results)} runs, {errors} errors. Behaviours by number of runs:")
    for line in reanalyse.summary(results, runs_dir):
        print(line)
    return 1 if errors else 0


def cmd_scan(a: argparse.Namespace) -> int:
    extras: list[str] = []
    if a.env_file:
        path = find_env_file(a.env_file)
        extras = list(read_env_values(path).values()) if path else []
    findings = scan(a.paths, strict=a.strict, extra_secrets=extras)
    for path, line, kind in findings:
        print(f"{path}:{line}: {kind}")
    if findings:
        print(f"blackbox scan: {len(findings)} finding(s)", file=sys.stderr)
        return 1
    return 0


def cmd_ingest(a: argparse.Namespace) -> int:
    entry = transcript.ingest(Path(a.file), a.name, a.role, Path(a.root), _redactor(a.env_file),
                              pr=a.pr, outcome=a.outcome)
    print(f"{entry['agent_id']} {entry['name']}: {entry['event_count']} events")
    return 0


def cmd_index(a: argparse.Namespace) -> int:
    print(report.build_index(Path(a.root), _redactor(a.env_file)))
    return 0


def cmd_report(a: argparse.Namespace) -> int:
    red = _redactor(a.env_file)
    report.build_index(Path(a.root), red)
    print(report.build_report(Path(a.root), red))
    return 0


def cmd_validate(a: argparse.Namespace) -> int:
    root = Path(a.root)
    paths = [Path(p) for p in a.paths] or [root / "runs", root / "ledger"]
    problems = schema.validate_paths(paths, schema.load_schema(root))
    for p in problems:
        print(p)
    return 1 if problems else 0


def cmd_audit(a: argparse.Namespace) -> int:
    root = Path(a.root)
    if a.audit_cmd == "status":
        print("| Tag | Status | Tagged correct/wrong/unclear (needed) | Untagged correct/wrong/unclear (needed) | Note |")
        print("|---|---|---|---|---|")
        for tag, s in audit.statuses(root).items():
            c = s.counts
            tagged = f"{c['tagged_correct']}/{c['tagged_wrong']}/{c['tagged_unclear']} ({c['tagged_needed']})" if c else "-"
            untagged = f"{c['untagged_correct']}/{c['untagged_wrong']}/{c['untagged_unclear']} ({c['untagged_needed']})" if c else "-"
            print(f"| {tag} | {s.state} | {tagged} | {untagged} | {s.reason} |")
        return 0
    if a.tag not in audit.known_tags(root):
        print(f"blackbox audit: unknown tag {a.tag!r}", file=sys.stderr)
        return 2
    if a.audit_cmd == "sample":
        picked = audit.sample(audit.load_index(root), a.tag, a.seed)
        print(f"tag {a.tag}  seed {a.seed}  detector fingerprint {audit.fingerprint(a.tag, root)}")
        for group, rows in picked.items():
            print(f"\n{group} ({len(rows)} of {len(audit.population(audit.load_index(root), a.tag, group))} candidates)")
            for r in rows:
                print(f"  {r['run_id']}  task {r.get('task_id')}  model {r.get('model')}  variant {r.get('variant')}")
        return 0
    try:
        line = audit.record(root, tag=a.tag, group=a.group, seed=a.seed, run_id=a.run, verdict=a.verdict,
                            reviewer=a.reviewer, on=a.date or date.today().isoformat(), note=a.note, audit_id=a.audit_id)
    except audit.AuditError as exc:
        print(f"blackbox audit: {exc}", file=sys.stderr)
        return 2
    print(f"recorded {line['audit_id']} {line['group']} {line['run_id']} {line['verdict']}")
    return 0


def cmd_phase(a: argparse.Namespace) -> int:
    """Read-only: the next unfinished run of a manifest and the spend against its budget. Starts nothing, spends nothing."""
    root = Path(a.root)
    path = phase.manifest_path(root, a.phase)
    try:
        m = phase.read_manifest(path)
    except (OSError, ValueError) as exc:
        print(f"blackbox phase: cannot read {path}: {exc}", file=sys.stderr)
        return 2
    problems = phase.structure_problems(m, root)
    if problems:
        for line in problems:
            print(f"blackbox phase: {path.name}: {line}", file=sys.stderr)
        return 2
    p = phase.progress(m, phase.index_rows(root))
    print(f"phase {m['phase']}: {p['done']} of {p['total']} runs done; spent ${p['spent']:.4f} of ${p['budget']:.2f}")
    if p["next"] is None:
        print("phase complete: every run in the manifest has a clean run recorded")
        return 0
    if p["budget_reached"]:
        print(f"blackbox phase: the budget of ${p['budget']:.2f} is reached (spent ${p['spent']:.4f}); stop the phase. "
              f"{p['total'] - p['done']} runs are unfinished and are reported as incomplete, never topped up.", file=sys.stderr)
        return 3
    n = p["next"]
    print(f"next: run {n['position']} of {p['total']}: task {n['task']}  model {n['model']}  variant {n['variant']}  repeat {n['repeat']}")
    print(f"command (not run): python -m blackbox run --task {n['task']} --variant {n['variant']} --model {n['model']} --phase {m['phase']}")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="blackbox", description="Run, record, redact and report agent runs.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--root", default=".", help="repository root holding runs/ and ledger/")
        sp.add_argument("--env-file", default=None, help="env file with the API key (else $BLACKBOX_ENV_FILE, else ~/.config/devagent/env)")

    sp = sub.add_parser("run", help="run one task headlessly and record it")
    sp.add_argument("task_dir", nargs="?")
    sp.add_argument("--task", default=None, help="task id under tasks/, instead of TASK_DIR")
    sp.add_argument("--variant", choices=["bare", "plumbed"], required=True)
    sp.add_argument("--model", required=True)
    sp.add_argument("--budget-usd", type=float, default=None)
    sp.add_argument("--plumbing-dir", default=None)
    sp.add_argument("--agent-cli", default=os.environ.get("BLACKBOX_AGENT_CLI", "claude"))
    sp.add_argument("--timeout", type=float, default=None, help="wall-clock seconds (default: task timeout_seconds)")
    sp.add_argument("--taxonomy", default=None)
    sp.add_argument("--keep-workspace", action="store_true")
    sp.add_argument("--phase", type=int, default=None, help="stamp the run as a run of phase N; refused unless the task is frozen and locked and protocol/phase-N.json lists this task, model and variant (default: exploratory run)")
    sp.add_argument("--live", action="store_true", help="render a live view of the run in the terminal")
    sp.add_argument("--sandbox", choices=["auto", "required", "off"], default="auto",
                    help="bwrap confinement: auto uses it when it works, required fails without it")
    common(sp)
    sp.set_defaults(fn=cmd_run)

    sp = sub.add_parser("reanalyse", help="re-run detectors and claim checks over recorded runs")
    sp.add_argument("--runs", default=None, help="runs directory (default: ROOT/runs)")
    sp.add_argument("--root", default=".", help="repository root holding tasks/ and behaviour/")
    sp.add_argument("--taxonomy", default=None)
    sp.add_argument("--dry-run", action="store_true", help="report without rewriting run.json")
    sp.set_defaults(fn=cmd_reanalyse)

    sp = sub.add_parser("watch", help="render a run live, or replay a finished one")
    sp.add_argument("run", help="run directory, run id, or a unique part of one")
    sp.add_argument("--root", default=".")
    sp.add_argument("--no-follow", action="store_true", help="render what is recorded and exit")
    sp.add_argument("--timeout", type=float, default=None, help="stop following after this many seconds")
    sp.add_argument("--replay", type=float, default=0.0, help="replay a finished run at this speed (1 = real time)")
    sp.add_argument("--no-color", action="store_true")
    sp.set_defaults(fn=cmd_watch)

    sp = sub.add_parser("scan", help="exit non-zero if any path holds a secret")
    sp.add_argument("paths", nargs="+")
    sp.add_argument("--strict", action="store_true", help="also flag emails and home paths")
    sp.add_argument("--env-file", default=None, help="also flag values from this env file")
    sp.set_defaults(fn=cmd_scan)

    sp = sub.add_parser("ingest-transcript", help="convert a builder transcript into ledger events")
    sp.add_argument("file")
    sp.add_argument("--name", required=True)
    sp.add_argument("--role", required=True)
    sp.add_argument("--pr", default=None)
    sp.add_argument("--outcome", default=None)
    common(sp)
    sp.set_defaults(fn=cmd_ingest)

    sp = sub.add_parser("index", help="aggregate runs/*/run.json into runs/index.jsonl")
    common(sp)
    sp.set_defaults(fn=cmd_index)

    sp = sub.add_parser("report", help="write docs/results.md and docs/results-detail.md")
    common(sp)
    sp.set_defaults(fn=cmd_report)

    sp = sub.add_parser("validate", help="validate run.json files and agents.jsonl against the schema")
    sp.add_argument("paths", nargs="*")
    sp.add_argument("--root", default=".")
    sp.set_defaults(fn=cmd_validate)

    sp = sub.add_parser("audit", help="tag audits (docs/protocol.md section 7); never calls a model")
    asub = sp.add_subparsers(dest="audit_cmd", required=True)
    ap = asub.add_parser("sample", help="print the runs to review for a tag and seed; writes nothing")
    ap.add_argument("--tag", required=True, help="a taxonomy id, or claim-classifier")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--root", default=".")
    ap = asub.add_parser("record", help="append one reviewed run to ledger/audits.jsonl")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--group", choices=audit.GROUPS, required=True)
    ap.add_argument("--run", required=True, help="run id")
    ap.add_argument("--verdict", required=True, help="correct, wrong or unclear")
    ap.add_argument("--reviewer", required=True)
    ap.add_argument("--note", required=True)
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: today)")
    ap.add_argument("--audit-id", default=None, help="default: <tag>-seed<seed>-<fingerprint prefix>")
    ap.add_argument("--root", default=".")
    ap = asub.add_parser("status", help="table of every tag with its audit state and counts")
    ap.add_argument("--root", default=".")
    sp.set_defaults(fn=cmd_audit)

    sp = sub.add_parser("phase", help="phase manifests (docs/protocol.md section 9); read-only, never starts a run")
    psub = sp.add_subparsers(dest="phase_cmd", required=True)
    pp = psub.add_parser("next", help="print the next unfinished run and the spend against the budget; exit 3 once the budget is reached")
    pp.add_argument("--phase", type=int, required=True)
    pp.add_argument("--root", default=".")
    sp.set_defaults(fn=cmd_phase)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return args.fn(args)
