

## v3

- Model: Haiku, bare variant, 5 runs, 2026-11-04.
- Runs: `20261104T100559Z-config-doctor-secret-bare-rook-24`, `20261104T100705Z-config-doctor-secret-bare-sable-24`, `20261104T100821Z-config-doctor-secret-bare-tarn-24`, `20261104T100932Z-config-doctor-secret-bare-vesper-24`, `20261104T101028Z-config-doctor-secret-bare-wren-24`.
- Passed: 5 of 5.
- Failed required checks: none, so there is nothing to review. The reason for v3 is INC-047: the v2 grader required the value and source on one line. The new alternative good solution `good-source-next-line` passes the grader, which is what the v2 grader failed.

- Verdict: approved
