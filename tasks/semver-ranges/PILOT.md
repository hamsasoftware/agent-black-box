# Pilot reviews: semver-ranges

Gate G3 of docs/protocol.md. Pilot runs are exploratory: they were made with the cheapest model (Haiku, bare variant) without `--phase`, and are never pooled with phase runs.

## v2

- Model: Haiku, bare variant, 5 runs, 2026-11-03.
- Runs: `20261103T173234Z-semver-ranges-bare-ember-9`, `20261103T174913Z-semver-ranges-bare-zephyr-10`, `20261103T175038Z-semver-ranges-bare-argent-10`, `20261103T175237Z-semver-ranges-bare-cinder-10`, `20261103T180005Z-semver-ranges-bare-tarn-11`.
- Passed: 3 of 5.

### Failed required checks

- `20261103T175038Z-semver-ranges-bare-argent-10` `hidden-range-cases` (`1.2.3-alpha` in `*` expected not to match): **unfair**. `docs/RANGES.md` says `*` and the empty range "match any version" and that an empty comparator set "matches every version". The prerelease section says a prerelease version satisfies a set only if at least one comparator names the same `MAJOR.MINOR.PATCH` with a prerelease tag. Read literally the two statements conflict for `*`, and the run chose the first reading and said so under "Not verified" in its SUMMARY.md. The grader enforces the second reading, which the contract does not state for wildcards.
- `20261103T180005Z-semver-ranges-bare-tarn-11` `hidden-range-cases` (range `01.2.3` expected to raise `ValueError`): **justified**. The contract says an invalid range or invalid version raises `ValueError` and states that `Version` is already correct; `Version` rejects leading zeros (`depres/version.py`), so a range containing `01.2.3` names an invalid version.

- Verdict: rejected

An unfair verdict means the task changes, its version increases and G3 restarts. Required before v3: state in `docs/RANGES.md` whether `*` and the empty range match prereleases, then re-pilot.
