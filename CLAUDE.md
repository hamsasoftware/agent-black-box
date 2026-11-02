@AGENTS.md

## Tool-specific

- Hooks in `.claude/hooks/` enforce the Never list. A block exits with code 2 and explains why; do not retry the same action another way.
- Every tool call is logged, redacted, to `.claude/logs/tool-calls.jsonl` (git-ignored).
- Named subagents live in `.claude/agents/`. Delegate only for independent work or a reduced tool set.
- Personal notes go in `CLAUDE.local.md`, which is git-ignored.
