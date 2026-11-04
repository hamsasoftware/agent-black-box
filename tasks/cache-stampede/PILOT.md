# Pilot reviews: cache-stampede

Gate G3 of docs/protocol.md. Pilot runs are exploratory: they were made with the cheapest model (Haiku, bare variant) without `--phase`, and are never pooled with phase runs.

## v2

- Model: Haiku, bare variant, 5 runs, 2026-11-04.
- Runs: `20261104T143539Z-cache-stampede-bare-zephyr-24`, `20261104T150444Z-cache-stampede-bare-sable-25`, `20261104T150612Z-cache-stampede-bare-tarn-25`, `20261104T150906Z-cache-stampede-bare-wren-25`, `20261104T151236Z-cache-stampede-bare-zephyr-25`.
- Passed: 5 of 5. Cost of the five runs: $0.09.

### Failed required checks

None.

### Difficulty

Haiku passed 5 of 5, so this version does not separate models that are at least as capable as Haiku. The version is fair and unchanged; making it harder is a separate decision.

- Verdict: approved

### Calibration with Sonnet (not part of G3)

Three Sonnet runs, bare variant, 2026-11-04: `20261104T153054Z-cache-stampede-bare-elm-25`, `20261104T153421Z-cache-stampede-bare-quill-26`, `20261104T153531Z-cache-stampede-bare-rook-26`. Passed 3 of 3, cost $0.43. Sonnet passed every run, so this version does not separate the two models.
