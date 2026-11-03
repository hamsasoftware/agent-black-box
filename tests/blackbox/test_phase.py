import copy
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from blackbox import phase
from blackbox.cli import main as cli

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("phase_manifest", ROOT / "scripts" / "phase_manifest.py")
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)

MODELS = ["claude-sonnet-5-5", "claude-haiku-4-5-20251001"]
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@users.noreply.github.com", "-c", "commit.gpgsign=false"]


def git(root, *args):
    return subprocess.run([*GIT, *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def write_task(root, name, frozen=True, version=1, body="a"):
    d = root / "tasks" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "task.yaml").write_text(yaml.safe_dump({"id": name, "version": version, "frozen": frozen}))
    (d / "PROMPT.md").write_text(body)


def write_lock(root):
    now = pm.task_lock.current(root)
    tasks = {n: {"version": e["version"], "sha256": e["sha256"]} for n, e in now.items() if e["frozen"]}
    (root / "tasks" / "LOCK.json").write_text(json.dumps({"protocol": 1, "tasks": tasks}))


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "schemas").mkdir(parents=True)
    shutil.copy(ROOT / "schemas" / "phase-manifest.schema.json", root / "schemas")
    for name in ("alpha", "beta"):
        write_task(root, name)
    write_task(root, "cand", frozen=False)
    write_lock(root)
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    return root


def args(**over):
    base = dict(phase=1, questions=["Q1"], models=list(MODELS), variants=["bare"], plumbed_model=None, tasks=["alpha", "beta"],
                repeats=3, seed=7, budget_usd=50.0, harness_commit=None)
    base.update(over)
    return type("A", (), base)()


def make(repo, **over):
    path, problems = pm.generate(repo, args(**over))
    assert not problems, problems
    return path


def load(path):
    return json.loads(path.read_text())


def save(path, m):
    path.write_text(json.dumps(m, indent=2))


# ---- the shuffle ---------------------------------------------------------------------------------------------------

def test_the_shuffle_is_pinned_so_it_cannot_drift_between_python_versions():
    # sha256 keys only: this literal result must never change
    m = {"tasks": {"a": {}, "b": {}}, "models": ["claude-m-1"], "variants": ["bare"], "plumbed_model": None, "repeats": 2, "seed": 1}
    assert [(r["task"], r["repeat"]) for r in phase.expected_runs(m)] == [("a", 2), ("b", 1), ("a", 1), ("b", 2)]


def test_the_same_seed_gives_the_same_order_and_another_seed_a_different_one(repo):
    a = load(make(repo, seed=7))["runs"]
    (repo / "protocol" / "phase-1.json").rename(repo / "protocol" / "x.json")
    b = load(make(repo, seed=7))["runs"]
    (repo / "protocol" / "phase-1.json").unlink()
    c = load(make(repo, seed=8))["runs"]
    assert a == b and a != c
    assert sorted(map(json.dumps, a)) == sorted(map(json.dumps, c))


# ---- generate ------------------------------------------------------------------------------------------------------

def test_generate_writes_the_full_cross_product_and_check_passes(repo):
    path = make(repo)
    m = load(path)
    assert len(m["runs"]) == 2 * 2 * 3
    assert m["harness_commit"] == git(repo, "rev-parse", "HEAD")
    assert m["tasks"]["alpha"] == {"version": 1, "sha256": pm.task_lock.read_lock(repo)["alpha"]["sha256"]}
    assert pm.check(repo) == []
    assert pm.main(["check", "--root", str(repo)]) == 0


def test_a_plumbed_phase_has_bare_for_all_models_and_plumbed_for_one(repo):
    m = load(make(repo, questions=["Q1", "Q2"], variants=["bare", "plumbed"], plumbed_model=MODELS[0]))
    cells = {(r["model"], r["variant"]) for r in m["runs"]}
    assert cells == {(MODELS[0], "bare"), (MODELS[0], "plumbed"), (MODELS[1], "bare")}
    assert len(m["runs"]) == 2 * 3 * 3


def test_generate_never_overwrites(repo):
    path = make(repo)
    before = path.read_text()
    _, problems = pm.generate(repo, args(seed=99))
    assert any("already exists" in p for p in problems)
    assert path.read_text() == before


def test_generate_refuses_a_candidate_and_a_missing_task(repo):
    _, p = pm.generate(repo, args(tasks=["alpha", "cand"]))
    assert any("cand is a candidate" in x for x in p)
    _, p = pm.generate(repo, args(tasks=["alpha", "ghost"]))
    assert any("ghost does not exist" in x for x in p)
    lock = json.loads((repo / "tasks" / "LOCK.json").read_text())
    del lock["tasks"]["beta"]
    (repo / "tasks" / "LOCK.json").write_text(json.dumps(lock))
    _, p = pm.generate(repo, args())
    assert any("beta is not in tasks/LOCK.json" in x for x in p)
    assert not (repo / "protocol").exists()


def test_generate_refuses_a_stale_lock(repo):
    (repo / "tasks" / "alpha" / "PROMPT.md").write_text("edited")
    _, p = pm.generate(repo, args())
    assert any("differs from tasks/LOCK.json" in x for x in p)


@pytest.mark.parametrize("over,needle", [
    (dict(variants=["bare", "plumbed"], plumbed_model=MODELS[0]), "without Q2"),
    (dict(questions=["Q1", "Q2"]), "cannot be answered"),
    (dict(questions=["Q1", "Q2"], variants=["bare", "plumbed"]), "plumbed_model"),
    (dict(questions=["Q1", "Q2"], variants=["bare", "plumbed"], plumbed_model="claude-other-1"), "plumbed_model"),
    (dict(plumbed_model=MODELS[0]), "plumbed_model"),
    (dict(variants=["plumbed"], questions=["Q2"], plumbed_model=MODELS[0]), "bare is required"),
    (dict(repeats=11), "repeats"),
    (dict(repeats=0), "repeats"),
    (dict(models=["sonnet"]), "models"),
    (dict(models=["claude-sonnet-latest"]), "not an exact model id"),
    (dict(models=["claude-sonnet"]), "not an exact model id"),
    (dict(models=["claude-sonnet-5-5[1m]"]), "models"),
    (dict(models=[MODELS[0], MODELS[0]]), "duplicate"),
    (dict(questions=["Q9"]), "questions"),
    (dict(budget_usd=0), "budget"),
    (dict(budget_usd=-5.0), "budget"),
])
def test_generate_refuses_designs_the_protocol_does_not_allow(repo, over, needle):
    path, problems = pm.generate(repo, args(**over))
    assert path is None and any(needle in p for p in problems), problems
    assert not (repo / "protocol").exists()


def test_generate_refuses_a_dirty_checkout_but_takes_an_explicit_commit(repo):
    (repo / "tasks" / "alpha" / "PROMPT.md").write_text("edited")
    _, p = pm.generate(repo, args(tasks=["beta"]))
    assert any("clean git checkout" in x for x in p)
    head = git(repo, "rev-parse", "HEAD")
    path, p = pm.generate(repo, args(tasks=["beta"], harness_commit=head))
    assert p == [] and load(path)["harness_commit"] == head


# ---- check ---------------------------------------------------------------------------------------------------------

def test_no_manifests_passes(repo):
    assert pm.main(["check", "--root", str(repo)]) == 0


def test_check_catches_a_stale_lock_after_the_manifest(repo):
    make(repo)
    write_task(repo, "alpha", version=2, body="changed")
    write_lock(repo)
    assert any("alpha is recorded at v1" in p for p in pm.check(repo))


def test_check_catches_a_task_edited_without_relocking(repo):
    make(repo)
    (repo / "tasks" / "beta" / "PROMPT.md").write_text("edited")
    assert any("beta differs from tasks/LOCK.json" in p for p in pm.check(repo))


def test_check_catches_a_task_that_became_a_candidate(repo):
    make(repo)
    write_task(repo, "beta", frozen=False)
    assert any("beta is a candidate" in p for p in pm.check(repo))


def mutate(repo, fn):
    path = repo / "protocol" / "phase-1.json"
    m = load(path)
    fn(m)
    save(path, m)
    return pm.check(repo)


def test_a_tampered_run_list_is_detected(repo):
    make(repo)
    assert any("missing" in p for p in mutate(repo, lambda m: m["runs"].pop()))


def test_a_reordered_run_list_is_detected(repo):
    make(repo)
    found = mutate(repo, lambda m: m["runs"].reverse())
    assert any("not in the order the seed gives" in p for p in found)


def test_a_changed_seed_is_detected(repo):
    make(repo)
    assert any("order" in p for p in mutate(repo, lambda m: m.update(seed=m["seed"] + 1)))


def test_a_duplicated_or_extra_run_is_detected(repo):
    make(repo)
    found = mutate(repo, lambda m: m["runs"].append(copy.deepcopy(m["runs"][0])))
    assert any("duplicate" in p for p in found)
    make_extra = mutate(repo, lambda m: m["runs"].__setitem__(0, {**m["runs"][0], "repeat": 99}))
    assert any("not part of the cross-product" in p for p in make_extra)


def test_widening_repeats_is_detected(repo):
    make(repo)
    assert pm.check(repo) == []
    assert any("repeats" in p for p in mutate(repo, lambda m: m.update(repeats=11)))


def test_an_alias_model_and_a_bad_budget_are_detected(repo):
    make(repo)
    assert any("not an exact model id" in p for p in mutate(repo, lambda m: m.update(models=["claude-sonnet-latest", MODELS[1]])))
    assert any("budget" in p for p in mutate(repo, lambda m: m.update(budget_usd=0)))
    assert any("budget" in p for p in mutate(repo, lambda m: m.update(budget_usd="50")))


def test_schema_violations_are_detected(repo):
    make(repo)
    assert any("missing seed" in p for p in mutate(repo, lambda m: m.pop("seed")))
    assert any("unexpected" in p for p in mutate(repo, lambda m: m.update(extra=1)))


def test_the_harness_commit_must_exist_in_history(repo):
    make(repo)
    assert any("not a commit" in p for p in mutate(repo, lambda m: m.update(harness_commit="0" * 40)))


def test_the_harness_commit_must_be_an_ancestor_of_head(repo):
    git(repo, "checkout", "-q", "-b", "side")
    (repo / "x.txt").write_text("x")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "side")
    side = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "-")
    assert any("not an ancestor" in p for p in mutate_commit(repo, side))


def mutate_commit(repo, sha):
    make(repo)
    return mutate(repo, lambda m: m.update(harness_commit=sha))


def test_the_file_name_must_match_the_phase(repo):
    make(repo)
    assert any("does not match the phase" in p for p in mutate(repo, lambda m: m.update(phase=2)))


def test_the_real_repository_has_a_schema_that_accepts_a_generated_manifest(repo):
    m = load(make(repo))
    from blackbox import schema
    assert schema.validate(m, phase.load_schema(ROOT), phase.load_schema(ROOT)) == []


# ---- phase next ----------------------------------------------------------------------------------------------------

def index_row(manifest, run, n, cost=1.0, **over):
    row = {"run_id": f"20261103T{n:06d}Z-{run['task']}-{run['variant']}-ember", "task_id": run["task"], "model": run["model"],
           "variant": run["variant"], "task_version": manifest["tasks"][run["task"]]["version"],
           "protocol_version": manifest["protocol_version"], "cost_usd": cost, "confounded_by": [], "started_at": f"2026-11-03T00:00:{n % 60:02d}Z"}
    row.update(over)
    return row


def write_index(root, rows):
    (root / "runs").mkdir(exist_ok=True)
    (root / "runs" / "index.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def nxt(root, *extra):
    return cli(["phase", "next", "--phase", "1", "--root", str(root), *extra])


def test_phase_next_starts_at_the_first_run_and_reports_progress(repo, capsys):
    m = load(make(repo))
    assert nxt(repo) == 0
    out = capsys.readouterr().out
    first = m["runs"][0]
    assert "0 of 12 runs done" in out and f"run 1 of 12: task {first['task']}" in out and f"model {first['model']}" in out
    assert "$0.0000 of $50.00" in out


def test_phase_next_skips_finished_runs_in_list_order(repo, capsys):
    m = load(make(repo))
    runs = m["runs"]
    write_index(repo, [index_row(m, runs[0], 1, cost=2.5), index_row(m, runs[1], 2, cost=1.5)])
    assert nxt(repo) == 0
    out = capsys.readouterr().out
    assert "2 of 12 runs done" in out and "$4.0000 of $50.00" in out
    third = runs[2]
    assert f"run 3 of 12: task {third['task']}  model {third['model']}  variant {third['variant']}" in out


def test_phase_next_ignores_confounded_runs_for_progress_but_counts_their_cost(repo, capsys):
    m = load(make(repo))
    write_index(repo, [index_row(m, m["runs"][0], 1, cost=3.0, confounded_by=["INC-1"])])
    assert nxt(repo) == 0
    out = capsys.readouterr().out
    assert "0 of 12 runs done" in out and "$3.0000" in out and "run 1 of 12" in out


def test_phase_next_ignores_exploratory_other_version_and_other_cell_rows(repo, capsys):
    m = load(make(repo))
    run = m["runs"][0]
    write_index(repo, [index_row(m, run, 1, protocol_version=None), index_row(m, run, 2, task_version=9),
                       index_row(m, run, 3, model="claude-other-1"), index_row(m, run, 4, task_id="ghost")])
    assert nxt(repo) == 0
    assert "0 of 12 runs done" in capsys.readouterr().out


def test_phase_next_since_keeps_an_earlier_phase_out(repo, capsys):
    m = load(make(repo))
    write_index(repo, [index_row(m, m["runs"][0], 1, started_at="2026-11-01T00:00:00Z")])
    assert nxt(repo, "--since", "2026-11-02T00:00:00Z") == 0
    assert "0 of 12 runs done" in capsys.readouterr().out


def test_phase_next_stops_at_the_budget_with_a_clear_message(repo, capsys):
    m = load(make(repo, budget_usd=5.0))
    write_index(repo, [index_row(m, m["runs"][0], 1, cost=3.0), index_row(m, m["runs"][1], 2, cost=2.0)])
    assert nxt(repo) == 3
    err = capsys.readouterr().err
    assert "budget of $5.00 is reached" in err and "10 runs are unfinished" in err


def test_phase_next_below_the_budget_still_runs(repo):
    m = load(make(repo, budget_usd=5.0))
    write_index(repo, [index_row(m, m["runs"][0], 1, cost=4.99)])
    assert nxt(repo) == 0


def test_phase_next_reports_a_finished_phase_even_when_over_budget(repo, capsys):
    m = load(make(repo, repeats=1, budget_usd=1.0))
    write_index(repo, [index_row(m, r, i, cost=1.0) for i, r in enumerate(m["runs"], 1)])
    assert nxt(repo) == 0
    assert "phase complete" in capsys.readouterr().out


def test_phase_next_refuses_a_missing_or_tampered_manifest(repo, capsys):
    assert nxt(repo) == 2
    path = make(repo)
    m = load(path)
    m["runs"].pop()
    save(path, m)
    assert nxt(repo) == 2
    assert "missing" in capsys.readouterr().err


def test_phase_next_never_writes(repo):
    make(repo)
    before = sorted(str(p.relative_to(repo)) for p in repo.rglob("*") if ".git" not in p.parts)
    nxt(repo)
    assert before == sorted(str(p.relative_to(repo)) for p in repo.rglob("*") if ".git" not in p.parts)
