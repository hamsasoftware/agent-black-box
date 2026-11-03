"""Phase manifests (docs/protocol.md section 9): build, verify and read protocol/phase-N.json. Never calls a model.

The run list is the full cross-product of tasks, models, the allowed variants and the repeats, in an order fixed by the
seed. The order is the ascending sha256 of "<seed>:<task>:<model>:<variant>:<repeat>" (lower-case hex), ties broken by
the tuple (task, model, variant, repeat); this uses only hashlib, so it is the same on every Python version.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

from blackbox import schema, taskspec

QUESTIONS = ("Q1", "Q2", "Q3", "Q4")
VARIANTS = ("bare", "plumbed")
DEFAULT_REPEATS = 10  # section 4: a manifest may narrow the default design, never widen it silently
SHUFFLE = "sha256-key:v1"
SHUFFLE_DOC = "ascending sha256 of '<seed>:<task>:<model>:<variant>:<repeat>', ties by (task, model, variant, repeat)"
SCHEMA = Path("schemas") / "phase-manifest.schema.json"
MODEL_ID = re.compile(r"^claude-[a-z0-9]+(?:-[a-z0-9]+)*$")
ALIAS_PARTS = {"latest", "default", "best", "alias"}


def manifest_path(root: Path, phase: int) -> Path:
    return root / "protocol" / f"phase-{phase}.json"


def load_schema(root: Path) -> dict[str, Any]:
    for base in (root, Path(__file__).resolve().parents[2]):
        if (base / SCHEMA).is_file():
            return json.loads((base / SCHEMA).read_text())
    raise FileNotFoundError(str(SCHEMA))


def run_key(seed: int, task: str, model: str, variant: str, repeat: int) -> tuple[str, tuple[str, str, str, int]]:
    digest = hashlib.sha256(f"{seed}:{task}:{model}:{variant}:{repeat}".encode()).hexdigest()
    return digest, (task, model, variant, repeat)


def variant_pairs(models: list[str], variants: list[str], plumbed_model: str | None) -> list[tuple[str, str]]:
    """(model, variant) pairs of the design: bare for every model, plumbed for the one named model."""
    pairs = []
    for model in models:
        for variant in variants:
            if variant == "plumbed" and model != plumbed_model:
                continue
            pairs.append((model, variant))
    return pairs


def expected_runs(m: dict[str, Any]) -> list[dict[str, Any]]:
    """The full shuffled run list a manifest's own fields imply."""
    cells = [(t, model, variant) for t in sorted(m["tasks"]) for model, variant in variant_pairs(m["models"], m["variants"], m.get("plumbed_model"))]
    keyed = [run_key(m["seed"], t, model, variant, r) for t, model, variant in cells for r in range(1, m["repeats"] + 1)]
    return [{"task": t, "model": model, "variant": variant, "repeat": r} for _, (t, model, variant, r) in sorted(keyed)]


def model_problems(models: list[str]) -> list[str]:
    out = []
    if len(set(models)) != len(models):
        out.append("models: duplicate id")
    for model in models:
        if not MODEL_ID.match(model) or not re.search(r"\d", model) or ALIAS_PARTS & set(model.split("-")) or "[" in model:
            out.append(f"models: {model!r} is not an exact model id (an alias, a family name or a floating tag)")
    return out


def design_problems(m: dict[str, Any]) -> list[str]:
    """Rules of section 4: a manifest narrows the default design, never widens it. `m` has already passed the schema."""
    out = model_problems(m["models"])
    for field in ("questions", "models", "variants"):
        if not m[field]:
            out.append(f"{field}: must not be empty")
    if not m["tasks"]:
        out.append("tasks: must not be empty")
    qs, variants, plumbed = m["questions"], m["variants"], m.get("plumbed_model")
    if len(set(qs)) != len(qs):
        out.append("questions: duplicate")
    if len(set(variants)) != len(variants):
        out.append("variants: duplicate")
    if "bare" not in variants:
        out.append("variants: bare is required for every model")
    if "plumbed" in variants and "Q2" not in qs:
        out.append("plumbed variant without Q2: section 4 allows plumbed only when the manifest lists Q2")
    if "Q2" in qs and "plumbed" not in variants:
        out.append("Q2 is listed but the plumbed variant is not, so Q2 cannot be answered")
    if "plumbed" in variants:
        if plumbed not in m["models"]:
            out.append("plumbed_model: must name exactly one of the listed models (plumbed runs for one model only)")
    elif plumbed is not None:
        out.append("plumbed_model: set but the plumbed variant is not")
    if m["repeats"] > DEFAULT_REPEATS:
        out.append(f"repeats: {m['repeats']} is above the default {DEFAULT_REPEATS}; the protocol must be changed first")
    if len(set(m["tasks"])) != len(m["tasks"]):
        out.append("tasks: duplicate")
    budget = m["budget_usd"]
    if not isinstance(budget, (int, float)) or isinstance(budget, bool) or not math.isfinite(budget) or budget <= 0:
        out.append("budget_usd: must be a positive number")
    return out


def run_list_problems(m: dict[str, Any]) -> list[str]:
    want, have = expected_runs(m), m["runs"]
    if have == want:
        return []
    ident = lambda r: (r["task"], r["model"], r["variant"], r["repeat"])  # noqa: E731
    want_set, have_set = {ident(r) for r in want}, [ident(r) for r in have]
    out = []
    if len(set(have_set)) != len(have_set):
        out.append("runs: contains a duplicate run")
    for r in sorted(want_set - set(have_set)):
        out.append(f"runs: missing {r}")
    for r in sorted(set(have_set) - want_set):
        out.append(f"runs: not part of the cross-product {r}")
    if not out:
        out.append("runs: same runs but not in the order the seed gives (re-derive with the documented shuffle)")
    return out


def structure_problems(m: Any, root: Path) -> list[str]:
    """Schema, design rules and run list. Reads nothing but the schema file."""
    errors = schema.validate(m, load_schema(root), load_schema(root))
    if errors:
        return errors
    if m["protocol_version"] > taskspec.PROTOCOL_VERSION:
        return [f"protocol_version: {m['protocol_version']} is newer than this checkout ({taskspec.PROTOCOL_VERSION})"]
    out = design_problems(m)
    if m["shuffle"] != SHUFFLE:
        out.append(f"shuffle: unknown algorithm {m['shuffle']!r}")
    if out:
        return out
    return run_list_problems(m)


def git_out(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=60)


def commit_problems(root: Path, commit: str) -> list[str]:
    try:
        if git_out(root, "rev-parse", "--git-dir").returncode != 0:
            return [f"harness_commit: {root} is not a git checkout"]
        if git_out(root, "cat-file", "-e", f"{commit}^{{commit}}").returncode != 0:
            return [f"harness_commit: {commit} is not a commit in this repository's history (a shallow clone needs fetch-depth 0)"]
        if git_out(root, "merge-base", "--is-ancestor", commit, "HEAD").returncode != 0:
            return [f"harness_commit: {commit} is not an ancestor of HEAD"]
    except (OSError, subprocess.SubprocessError) as exc:
        return [f"harness_commit: git failed: {exc}"]
    return []


def read_manifest(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# ---- phase next -------------------------------------------------------------------------------------------------

def index_rows(root: Path) -> list[dict[str, Any]]:
    path = root / "runs" / "index.jsonl"
    rows = []
    if path.is_file():
        for line in path.read_text().splitlines():
            try:
                row = json.loads(line) if line.strip() else None
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("run_id"):
                rows.append(row)
    return rows


def matching(m: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Index rows that belong to the manifest: stamped `phase == N` by the runner (which refuses the stamp unless the run
    was in the manifest) and of a listed task, model and variant. Ordered by run id (a timestamp)."""
    cells = {(t, model, variant) for t in m["tasks"] for model, variant in variant_pairs(m["models"], m["variants"], m.get("plumbed_model"))}
    out = [r for r in rows if r.get("phase") == m["phase"] and not isinstance(r.get("phase"), bool)
           and (r.get("task_id"), r.get("model"), r.get("variant")) in cells]
    return sorted(out, key=lambda r: str(r["run_id"]))


def progress(m: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Where a phase stands. The n-th clean run of a cell fills that cell's n-th slot in run-list order. Spend counts every
    matching run, confounded ones too, because the money is gone either way."""
    mine = matching(m, rows)
    done_per_cell: dict[tuple[str, str, str], int] = {}
    for r in mine:
        if not r.get("confounded_by"):
            cell = (r["task_id"], r["model"], r["variant"])
            done_per_cell[cell] = done_per_cell.get(cell, 0) + 1
    seen: dict[tuple[str, str, str], int] = {}
    done, nxt = 0, None
    for i, run in enumerate(m["runs"]):
        cell = (run["task"], run["model"], run["variant"])
        seen[cell] = seen.get(cell, 0) + 1
        if seen[cell] <= done_per_cell.get(cell, 0):
            done += 1
        elif nxt is None:
            nxt = {**run, "position": i + 1}
    spent = sum(float(r.get("cost_usd") or 0) for r in mine)
    return {"done": done, "total": len(m["runs"]), "next": nxt, "spent": spent, "budget": float(m["budget_usd"]),
            "budget_reached": spent >= float(m["budget_usd"])}
