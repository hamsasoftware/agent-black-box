# Pilot reviews: unit-migration-sweep

Gate G3 of docs/protocol.md. Pilot runs are exploratory: they were made with the cheapest model (Haiku, bare variant) without `--phase`, and are never pooled with phase runs.

## v2

- Model: Haiku, bare variant, 5 runs, 2026-11-04.
- Runs: `20261104T143737Z-unit-migration-sweep-bare-argent-24`, `20261104T151013Z-unit-migration-sweep-bare-yarrow-25`, `20261104T151414Z-unit-migration-sweep-bare-argent-25`, `20261104T151654Z-unit-migration-sweep-bare-birch-25`, `20261104T151924Z-unit-migration-sweep-bare-cinder-25`.
- Passed: 5 of 5. Cost of the five runs: $0.16.

### Failed required checks

None. Four runs failed only the advisory `no-gram-names-left` check (a gram-named identifier such as `total_g` or `MAX_TOTAL_G` left in a migrated module), which does not fail a run.

### Difficulty

Haiku passed 5 of 5, so this version does not separate models that are at least as capable as Haiku. The version is fair and unchanged; making it harder is a separate decision.

- Verdict: approved

### Calibration with Sonnet (not part of G3)

Three Sonnet runs, bare variant, 2026-11-04: `20261104T153242Z-unit-migration-sweep-bare-ember-26`, `20261104T153643Z-unit-migration-sweep-bare-sable-26`, `20261104T153834Z-unit-migration-sweep-bare-tarn-26`. Passed 3 of 3, cost $0.93. Sonnet passed every run, so this version does not separate the two models.
