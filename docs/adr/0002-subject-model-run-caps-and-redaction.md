# 2. One subject model, capped runs, redaction before commit

Date: 2026-11-02

Status: Accepted

## Context

The project compares agent behaviour across tasks and across two variants: a bare agent and the same agent with plumbing (instruction file, permissions, hooks, subagents). For a comparison to mean anything, the variant has to be the only thing that changes.

Real runs cost money and run code the agent writes. An agent can loop, run for a long time or try destructive commands.

Run data is a full record of a session: every message, tool call and diff. Agents read environment files and print what they find, so a raw record can contain API keys and other secrets. This repository is public, and git history is hard to clean once pushed.

## Decision

1. **One subject model.** All subject runs use a single, everyday, affordable coding model, chosen and justified in `docs/model-choice.md`. Its exact model id is recorded in every `run.json`, together with the CLI version. Changing the model is a new decision, recorded in a new ADR, and old and new runs are not pooled.
2. **Caps on every run.** Each task declares `timeout_seconds`, `max_budget_usd` and `max_turns` in `task.yaml`, and the harness enforces all three. Runs execute in a temporary workspace. Real runs start only when a person or the coordinator starts them, never from the test suite or CI. Every run records `cost_usd` and `budget_usd`.
3. **Redaction before commit.** The harness redacts every artefact before it is written into `runs/`. A secret scan (`make scan` locally, the `secret-scan` job in CI) must pass before run data is merged. API keys come from an environment file named at runtime and are passed only to the agent subprocess.

## Consequences

- Differences between bare and plumbed runs can be attributed to the plumbing, not to a model change. Findings do not automatically generalise to other models.
- An affordable model makes repeated runs possible, and is closer to what most teams use every day.
- Caps bound the cost of a bad run and make runaway behaviour a recorded outcome (`stop_reason`) instead of an open-ended bill. A cap can cut off a run that would have succeeded; tasks must set caps with headroom.
- Redaction can remove context a reader would want. Redaction markers keep the shape of the data so evidence indexes stay valid.
- A secret the redactor misses can still reach a pull request. The scan is the second line of defence, and SECURITY.md describes what to do if both fail.
