## Task

<!-- Task id and one-sentence summary. -->

Closes #

## Trap

<!-- What makes the wrong path attractive, and which taxonomy ids the task targets (they must match `traps` in task.yaml). -->

## Grader

- [ ] The reference solution passes: `python grader/run.py <workspace>` prints `"passed": true`.
- [ ] A cheating solution is rejected (describe it below and paste the grader output).
- [ ] The grader runs offline with the standard library or pytest only.
- [ ] The grader is not visible to the agent during a run.

<!-- Cheating solution and grader output. -->

## Difficulty rationale

<!-- Why the task is medium or hard, and what a capable agent must do to pass. -->

## Files

- [ ] `task.yaml` with `id`, `title`, `difficulty`, `traps`, `timeout_seconds`, `max_budget_usd`, `max_turns`
- [ ] `PROMPT.md`
- [ ] `fixture/`
- [ ] `grader/run.py`
- [ ] `NOTES.md`

## Checklist

- [ ] No secrets are included and `make scan` passed.
- [ ] Real-run cost for this change in USD, or none:
- [ ] The change contains no unrelated edits.
