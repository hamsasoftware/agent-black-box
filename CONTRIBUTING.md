# Contributing

Thanks for helping. This project records what coding agents actually do, so the bar for a change is evidence: a test, a grader result or a dated source.

## Quickstart

You need Python 3.11 or newer, `git` and `make`.

```sh
git clone https://github.com/hamsasoftware/agent-black-box.git
cd agent-black-box
make setup        # create .venv and install dev tools
make test         # offline tests; never spends money
make run-task TASK=<task-id> VARIANT=bare MODEL=<model-id> [BUDGET=<usd>]   # one real run; spends money
```

`make help` lists every command. `make run-task` needs an API key in an environment file that the harness names at runtime (see `docs/ledger.md`). The key is passed only to the agent subprocess and must never be committed.

## Branches and commits

- Branch from `main` as `type/short-topic`, for example `feat/version-trap-task`, `fix/redactor-bearer`, `docs/ledger-fields`. Types: `feat`, `fix`, `docs`, `test`, `chore`, `ci`.
- Write commit subjects in the imperative, under 72 characters, for example `Add grader check for edited tests`. Explain why in the body when it is not obvious.
- One logical change per pull request. Do not mix a new task with harness changes.
- Stay inside the paths your change is about. The module table in [ARCHITECTURE.md](ARCHITECTURE.md) lists who owns what.

## Test first

Write the failing test before the fix or feature, then make it pass. `make test` must stay offline and free: tests never call a model or spend money. Real runs happen only when a maintainer starts them.

## Adding a task

1. Open a [task proposal](https://github.com/hamsasoftware/agent-black-box/issues/new?template=task_proposal.yml) first: the trap, the failure mode it should provoke, and how a grader detects it.
2. Create `tasks/<task-id>/` in the format described in [ARCHITECTURE.md](ARCHITECTURE.md#task-format): `task.yaml`, `PROMPT.md`, `fixture/`, `grader/`, `NOTES.md`.
3. Pin the criteria as the [evaluation protocol](docs/protocol.md) requires. In `task.yaml` set `version` and `frozen: false`, list the `rules` the agent is shown, and declare every check the grader emits with a class (`rule`, `result`, `trap` or `advisory`) and a reason. In `NOTES.md` add the Criteria, Hidden by design and Version history sections. `tests/tasks/test_tasks_criteria.py` fails until this is complete.
4. Add solutions under `tests/tasks/solutions/<task-id>/`: the reference (`good`), at least one alternative good solution, cheating solutions, and the rule-breaking solutions `rule-out-of-scope`, `rule-edits-test` and `rule-no-summary`. Every required check must be failed by at least one of them.
5. Graders run offline with the standard library or pytest only, and are never visible to the agent.
6. A task becomes usable in a phase only after a pilot review (`PILOT.md`) and `python scripts/task_lock.py write`. Changing a frozen task means raising its `version` first.
7. Open the pull request with the task template: add `?template=task.md` to the compare URL.

## Proposing a practice

Practices for the agent instruction file, permissions, hooks and subagents must cite a source with a URL and a publication date. Open a [practice suggestion](https://github.com/hamsasoftware/agent-black-box/issues/new?template=practice_suggestion.yml) with the source, its date, a supporting quote and the behaviour you expect it to change. A practice is adopted only when a bare-versus-plumbed comparison supports it, or when it is recorded as unproven.

## Run data

Anything under `runs/` comes from a real agent session and may contain secrets the agent saw.

- Run data is redacted by the harness before it is written to the repository. Never hand-edit or commit raw transcripts.
- Run `make scan` before every commit that touches run data. It must report no findings.
- If you find a secret in committed data, do not open a public issue. Follow [SECURITY.md](SECURITY.md).

## Recording an error

When you find a mistake in the harness, a detector, a task, CI, a guard or in how a change was reviewed, add an entry to `ledger/incidents.jsonl` in the same pull request as the fix, then run `python scripts/incidents.py render`. Record only what you know: leave a time as `null` rather than guessing it. The fields are checked by `make lint`, and [docs/incidents.md](docs/incidents.md) explains the aim. Name the agents involved and cite the commit, the run ids and the test that now prevents a repeat.

## Pull request checklist

The [pull request template](.github/PULL_REQUEST_TEMPLATE.md) asks for:

- Purpose and the linked issue (`Closes #n`).
- Evidence: run ids and grader results for any claim about behaviour.
- Tests run and their results.
- Real-run cost in USD, or none.
- No secrets, `make scan` passed, run data redacted, docs updated, no unrelated changes.

### Automatic checks on every pull request

The `Pull request requirements` workflow runs `scripts/check_pr_requirements.py` and fails the pull request unless:

- the description keeps the template's six sections in order, with none left empty and a `Closes` line, at least one type ticked, a dollar amount or `none` for the cost, and every checklist item ticked or marked not applicable;
- the title, description, branch name and every commit message avoid the forbidden wording listed in the script;
- the branch is named `type/short-topic`;
- every commit uses a GitHub no-reply address for author and committer. Set it once with `git config user.email ID+USERNAME@users.noreply.github.com`; the number and name are on your GitHub email settings page. Never commit with a private address in a public repository.

## Conduct

Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).
