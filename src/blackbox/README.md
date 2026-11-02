# blackbox

The harness: runs one task headlessly with the agent CLI, records a redacted ledger, grades, and tags behaviours. Field-level detail is in [docs/ledger.md](../../docs/ledger.md).

## Commands

```
python -m blackbox run TASK_DIR|--task ID --variant bare|plumbed --model ID [--budget-usd N] [--plumbing-dir DIR] [--sandbox auto|required|off]
python -m blackbox run ... --live                # same, with a live terminal view
python -m blackbox watch RUN [--no-follow] [--replay N]   # follow or replay a run
python -m blackbox reanalyse [--runs DIR] [--dry-run]   # re-run detectors over recorded runs
python -m blackbox scan PATH...                 # exit 1 on a secret
python -m blackbox ingest-transcript FILE --name NAME --role ROLE
python -m blackbox index                        # runs/index.jsonl
python -m blackbox report                       # docs/results.md
python -m blackbox validate [PATH...]           # check against schemas/ledger.schema.json
```

The `blackbox` console script is the same entry point.

## Modules

| Module | Job |
|---|---|
| `cli.py` | Argument parsing and the commands above. |
| `runner.py` | Workspace, baseline commit, agent launch, timeout, diff, grader, writing the run. |
| `envfile.py` | Finds the env file and builds the agent's minimal environment; the key goes nowhere else. |
| `confine.py` | Prepares the confinement layers: private home and config, deny rules, guard hook, sandbox choice. |
| `sandbox.py` | Builds the bubblewrap command line and probes whether bubblewrap works here. |
| `guard.py` | Standalone hook script and shared logic that tell real escapes from scratch files and text that merely contains a slash. |
| `stream.py` | Parses stream-json lines into tool uses, tool results, texts, usage, cost and denials. |
| `behaviours.py` | Detector registry; each detector returns evidence as event indexes and a reason. |
| `taxonomy.py` | Reads `behaviour/taxonomy.yaml`, with the agreed ids as a fallback. |
| `claims.py` | Extracts claims from the final message and checks them against the grade, tool results and diff. |
| `redact.py` | Redactor and secret scanner. |
| `ledger.py` | Roster names, agent ids, JSON and JSONL writers (always through the redactor). |
| `transcript.py` | Builder transcript ingestion into `ledger/builders/`. |
| `reanalyse.py` | Re-runs detectors and claim checks over recorded runs and rewrites those fields in place. |
| `report.py` | `runs/index.jsonl` (with `confounded_by` from `ledger/incidents.jsonl` and `claim_outcome`) and `docs/results.md` (clean-run results, claims versus grader, confounded runs). |
| `live.py` | Terminal live view (ANSI only) for `run --live` and `watch`. |
| `schema.py` | Small JSON Schema validator for the ledger schema. |

## How a run flows

`run` loads `task.yaml` and the env file, takes the next roster name, copies `fixture/` (and the plumbing for `plumbed`) into a temp workspace, commits a baseline, prepares confinement (sandbox, private home, deny rules, guard hook), creates `runs/<run_id>/` with `live.json`, launches the agent CLI and appends each redacted event to `events.jsonl` as it arrives (and to the live view with `--live`), stops it on exit or timeout, diffs the workspace against the baseline, copies and runs the hidden grader, runs the detectors and claim checks, then redacts and writes `diff.patch`, `grade.json` and `run.json`, removes `live.json`, and appends the subject to `ledger/agents.jsonl`.
