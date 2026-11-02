# Architecture

## Modules and owners

Each module has one owner agent. Owners edit only their own paths. The coordinator owns this file, `README.md` and the generated `runs/` and `ledger/` data.

| Module | Paths | Owner | Job |
|---|---|---|---|
| Research | `docs/best-practices.md`, `docs/sources.json`, `docs/model-choice.md` | Atlas | Recent (2025 to 2026) industry practice for agent instruction files, permissions, hooks, subagents, evaluation and tracing, every claim cited with a URL and a date. |
| Plumbing | `AGENTS.md`, `CLAUDE.md`, `.claude/**`, `plumbing/**`, `.github/**`, `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CODEOWNERS`, `.editorconfig`, `Makefile`, `docs/adr/**`, `scripts/**` | Forge | The agent plumbing itself, built from Atlas's findings, plus repository hygiene and CI. |
| Harness | `src/blackbox/**`, `tests/blackbox/**`, `pyproject.toml`, `schemas/**`, `docs/ledger.md` | Tally | Runs tasks headlessly, records the ledger, redacts secrets, grades, and tags behaviours. |
| Tasks | `tasks/**`, `behaviour/taxonomy.yaml`, `tests/tasks/**` | Gauntlet | Challenging tasks with fixtures, hidden graders and documented traps, and the behaviour taxonomy. |
| Video | `video/**`, `docs/video.md` | Reel | Builds the narrated replay video from recorded run data. |

## Task format

Each task is a directory `tasks/<task-id>/`:

- `task.yaml`: `id`, `title`, `difficulty` (medium or hard), `traps` (list of taxonomy ids the task is designed to provoke), `timeout_seconds`, `max_budget_usd`, `max_turns`.
- `PROMPT.md`: the exact prompt given to the agent.
- `fixture/`: the starting project, copied into a temporary workspace for each run.
- `grader/`: hidden checks run after the agent finishes, never visible to the agent. Run with `python grader/run.py <workspace>`, which prints one JSON object: `{"passed": bool, "score": 0 to 1, "checks": [{"name", "passed", "detail"}]}`.
- `NOTES.md`: what the task tests, what good and bad behaviour look like, and what the trap is.

Graders run offline with the standard library or pytest only.

## Run ledger

One JSON object per run in `runs/<run_id>/run.json`, plus `events.jsonl` (every message and tool call, redacted), `diff.patch`, and `grade.json`. Aggregates go in `runs/index.jsonl`. Required fields in `run.json`:

`run_id`, `agent_id`, `agent_name`, `kind` (`subject`), `model`, `claude_cli_version`, `session_id`, `task_id`, `variant` (`bare` or `plumbed`), `prompt_sha256`, `started_at`, `ended_at`, `duration_ms`, `turns`, `tool_calls` (count by tool), `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `cost_usd`, `budget_usd`, `stop_reason`, `permission_denials`, `files_changed`, `grade` (the grader JSON), `claims` (what the agent said it did, extracted), `verified_claims` (which claims the grader or tooling confirmed), `behaviours` (taxonomy ids observed, each with `evidence` pointing at event indexes), and `notes`.

Builder agents (the agents that build this repository) are recorded in `ledger/agents.jsonl` with: `agent_id`, `name`, `role`, `kind` (`builder`), `model`, `started_at`, `ended_at`, `duration_ms`, `tool_uses`, `tokens`, `pr`, `outcome`, `blocked_actions`.

## Agent names

Builders: Atlas (research), Forge (plumbing), Tally (harness), Gauntlet (tasks), Reel (video). Subjects get names from this list in order, one per run: Ember, Quill, Rook, Sable, Tarn, Vesper, Wren, Yarrow, Zephyr, Argent, Birch, Cinder, Dune, Elm, Flint. Names repeat with a numeric suffix after the list is used.

## Safety rules

- API keys come from an environment file named at runtime and are handed only to the agent subprocess. They are never printed, logged or committed.
- Every committed artefact passes the redactor and a secret scan.
- Candidate code runs inside a temporary workspace with a spending cap and a turn cap.
- Real runs spend money. They run only when a human or the coordinator starts them, never in the test suite.

## Contract updates

Agreed after the harness landed.

- Optional `task.yaml` keys: `scope` (paths the agent may change), `injection_markers` (strings that, if the agent acts on them, mean an injected instruction was followed), `expected_diff_lines` (an upper bound for a minimal diff). Detectors for scope creep, injection and overengineering need these keys.
- Grader naming convention: a check whose name starts with `instruction` records whether the agent obeyed an explicit instruction in the prompt.
- Extra `run.json` fields: `exit_code`, `max_turns`, `timeout_seconds`, `allowed_tools`, `event_count`. Each entry in `behaviours` carries a `polarity` and a `confidence`. Each entry in `claims` carries a `status`.
- Subject agents must stay inside their task workspace. Access outside it is recorded as the behaviour `out-of-workspace-access` and, where the platform allows, blocked.
