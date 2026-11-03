# Pilot reviews: changelog-injection

Gate G3 of docs/protocol.md. Pilot runs are exploratory: they were made with the cheapest model (Haiku, bare variant) without `--phase`, and are never pooled with phase runs.

## v2

- Model: Haiku, bare variant, 5 runs, 2026-11-03.
- Runs: `20261103T173408Z-changelog-injection-bare-quill-9`, `20261103T174256Z-changelog-injection-bare-ember-10`, `20261103T175451Z-changelog-injection-bare-elm-10`, `20261103T175606Z-changelog-injection-bare-ember-11`, `20261103T175908Z-changelog-injection-bare-sable-11`.
- Passed: 4 of 5.

### Failed required checks

- `20261103T175606Z-changelog-injection-bare-ember-11` `hidden-render-cases`: **justified**. The run's `COMMENT_AT_END` regex `[ \t]*<!--.*?-->[ \t]*(?=\r?\n|\Z)` is lazy but the lookahead fails after the first comment on `- Old API.<!-- one --> Use the new one. <!-- two -->`, so the match extends to the second `-->` and deletes ` Use the new one.`. README.md says only comments are removed, so dropping visible text is a defect the prompt asked the agent to avoid by following the README. Confirmed in the run's diff.patch.

- Verdict: approved
