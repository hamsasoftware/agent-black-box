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
| `blocked_actions` | Denied or blocked tool calls, with event indexes. |

Subjects also carry `run_id`, `task_id` and `variant`, which lead to `runs/<run_id>/`.

## builders/

`builders/<name>/events.jsonl` holds the redacted, shortened event log of each builder agent, produced by:

```
python -m blackbox ingest-transcript TRANSCRIPT.jsonl --name NAME --role ROLE [--pr URL] [--outcome TEXT]
```

Each line is one message block (`text`, `tool_use`, `tool_result`, `thinking` length, or attachment type) tagged with the builder's `agent_id`.
