# ledger

Who did what. Every agent, builder or subject, has a name and an id and appears in `agents.jsonl`. Everything here has passed the redactor. Field-level detail is in [docs/ledger.md](../docs/ledger.md).

## agents.jsonl

One JSON object per line:

| Field | Meaning |
|---|---|
| `agent_id` | `agt-` plus 8 hex characters. |
| `name`, `role`, `kind` | Roster name, job, and `builder` or `subject`. |
| `model` | Model id the agent ran on. |
| `started_at`, `ended_at`, `duration_ms` | When it worked and for how long. |
| `tool_uses` | Number of tool calls. |
| `tokens` | `{input, output, cache_read, cache_creation}`. |
| `pr` | Pull request URL for builders; null for subjects. |
| `outcome` | Builders: as recorded at ingestion. Subjects: `passed`, `failed` or the stop reason. |
| `blocked_actions` | Denied or hook-blocked tool calls, with event indexes (`reason` is `permission` or `hook` for subjects). |

Subjects also carry `run_id`, `task_id` and `variant`, which lead to `runs/<run_id>/`.

## incidents.jsonl

The incident log (rendered to `docs/incidents.md`). `blackbox index` and `blackbox report` read it: every run listed in `affected.runs` of an incident with `invalidates_results: true` is marked `confounded_by` that incident in `runs/index.jsonl` and left out of the pass rates and means in `docs/results.md`, which lists it separately.

## audits.jsonl

Tag audits, one line per reviewed run, written only by `python -m blackbox audit record`. A tag is counted in `docs/results.md` only while its latest audit has passed. Fields and rules: [docs/ledger.md](../docs/ledger.md#ledgerauditsjsonl-fields).

## builders/

`builders/<name>/events.jsonl` holds the redacted, shortened event log of each builder agent, produced by:

```
python -m blackbox ingest-transcript TRANSCRIPT.jsonl --name NAME --role ROLE [--pr URL] [--outcome TEXT]
```

Each line is one message block (`text`, `tool_use`, `tool_result`, `thinking` length, or attachment type) tagged with the builder's `agent_id`.
