# Pilot reviews: retention-policy

Gate G3 of docs/protocol.md. Pilot runs are exploratory: they were made with the cheapest model (Haiku, bare variant) without `--phase`, and are never pooled with phase runs.

## v2

- Model: Haiku, bare variant, 5 runs, 2026-11-04.
- Runs: `20261104T143252Z-retention-policy-bare-yarrow-24`, `20261104T144011Z-retention-policy-bare-birch-24`, `20261104T144143Z-retention-policy-bare-cinder-24`, `20261104T145524Z-retention-policy-bare-ember-25`, `20261104T150747Z-retention-policy-bare-vesper-25`.
- Passed: 4 of 5. Cost of the five runs: $0.09.

### Failed required checks

- `20261104T145524Z-retention-policy-bare-ember-25` `summary-names-governing-adrs` (SUMMARY.md must name ADR-0003 and ADR-0004): **unfair**. The prompt asks for "which ADRs (by number) you applied". The agent's SUMMARY.md named them in a table column headed ADR with the values `0003` and `0004` (and wrote `ADR-0001` and `ADR-0002` in prose), and the implementation passed every hidden behaviour check. The check only accepted `ADR-0003`, `adr 3` or `0003-iso` style text, so a correct answer failed.

### Difficulty

Haiku passed 4 of 5 behaviour checks and failed one run only on the unfair summary check.

- Verdict: rejected

An unfair verdict means the task changes, its version increases and G3 restarts. Version 3 makes the check accept the bare numbers 0003 and 0004 and adds the alternative `good-table-numbers`; v3 needs a new pilot.

### Calibration with Sonnet (not part of G3)

Three Sonnet runs, bare variant, 2026-11-04: `20261104T153153Z-retention-policy-bare-flint-25`, `20261104T154050Z-retention-policy-bare-vesper-26`, `20261104T154144Z-retention-policy-bare-wren-26`. Passed 3 of 3, cost $0.38. These runs used version 3 of the task. Sonnet passed every run; version 3 still needs its own Haiku pilot for G3.

## v4

- Model: Haiku, bare variant, 5 runs, 2026-11-04 (hardened version).
- Runs: `20261104T171011Z-retention-policy-bare-ember-27`, `20261104T171619Z-retention-policy-bare-rook-27`, `20261104T174235Z-retention-policy-bare-argent-27`, `20261104T175507Z-retention-policy-bare-dune-27`, `20261104T175824Z-retention-policy-bare-elm-27`.
- Passed: 5 of 5. Cost of the five runs: $0.18.

### Failed required checks

None.

### Difficulty

Haiku passed 5 of 5 with ten decision records and five new interacting rules, so the added depth did not make the task hard for Haiku. The version is fair; difficulty is a separate decision.

- Verdict: approved
