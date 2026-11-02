# runs

One directory per recorded run of a subject agent on a task. Everything here has passed the redactor. Field-level detail is in [docs/ledger.md](../docs/ledger.md).

## Run ids

`<UTC start>-<task id>-<variant>-<name>`, for example `20261102T194422Z-off-by-one-bare-ember`. The name is the subject's roster name, lower-cased.

## Files in a run directory

| File | What it is |
|---|---|
| `run.json` | The record: model, cost, tokens, turns, tool counts, stop reason, permission denials and hook blocks, confinement layers, files changed, grade, claims, behaviours with evidence, notes. |
| `events.jsonl` | Every stream event in order, as `{"i", "t_ms", "event"}`, appended as it arrives. Behaviour evidence and claims point at `i`. |
| `diff.patch` | What the agent changed, against the baseline commit of the fixture. |
| `grade.json` | The hidden grader's verdict and checks. |
| `live.json` | Present only while the run is in progress (`status: running`), or if the harness failed (`status: failed`). |

## Reading a run

`python -m blackbox watch <run id or part of it>` renders a run in the terminal: live while it is in progress, or a finished one (`--replay 4` replays it at 4 times real speed).

1. Open `run.json`: `grade.passed`, `stop_reason`, `cost_usd`, `confinement.layers`, then `behaviours`.
2. For each behaviour, look up its `evidence[].event` indexes in `events.jsonl`.
3. Compare `claims` (what the agent said) with `verified_claims` and `grade` (what was checked).
4. Read `diff.patch` for the actual change.

## Regenerating aggregates

```
python -m blackbox reanalyse  # re-runs the detectors and claim checks after a detector change
python -m blackbox index      # rewrites runs/index.jsonl from runs/*/run.json
python -m blackbox report     # rewrites docs/results.md
python -m blackbox validate   # checks every run.json and ledger/agents.jsonl
python -m blackbox scan runs ledger
```
