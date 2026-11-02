# blackbox

The harness: runs one task headlessly with the agent CLI, records a redacted ledger, grades, and tags behaviours. Field-level detail is in [docs/ledger.md](../../docs/ledger.md).

## Commands

```
python -m blackbox run TASK_DIR --variant bare|plumbed --model ID [--budget-usd N] [--plumbing-dir DIR]
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
| `envfile.py` | Finds the env file and builds the agent's environment; the key goes nowhere else. |
| `stream.py` | Parses stream-json lines into tool uses, tool results, texts, usage, cost and denials. |
| `behaviours.py` | Detector registry; each detector returns evidence as event indexes and a reason. |
| `taxonomy.py` | Reads `behaviour/taxonomy.yaml`, with the agreed ids as a fallback. |
| `claims.py` | Extracts claims from the final message and checks them against the grade, tool results and diff. |
| `redact.py` | Redactor and secret scanner. |
| `ledger.py` | Roster names, agent ids, JSON and JSONL writers (always through the redactor). |
| `transcript.py` | Builder transcript ingestion into `ledger/builders/`. |
| `report.py` | `runs/index.jsonl` and `docs/results.md`. |
| `schema.py` | Small JSON Schema validator for the ledger schema. |

## How a run flows

`run` loads `task.yaml` and the env file, takes the next roster name, copies `fixture/` (and the plumbing for `plumbed`) into a temp workspace, commits a baseline, launches the agent CLI with stdout captured line by line, stops it on exit or timeout, diffs the workspace against the baseline, copies and runs the hidden grader, runs the detectors and claim checks, then redacts and writes `runs/<run_id>/events.jsonl`, `diff.patch`, `grade.json` and `run.json`, and appends the subject to `ledger/agents.jsonl`.
