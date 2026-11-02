# agent-black-box

A flight recorder for AI coding agents.

This repository exists to answer one question with evidence: **what makes a coding agent behave well, and what makes it behave badly?** It does that in four ways:

1. **Challenging tasks** with hidden graders and deliberate traps (ambiguous specs, misleading tests, injected instructions, version traps, tempting shortcuts).
2. **A run ledger** that records every data point of every agent run: agent id, name, model, prompt hash, every tool call, tokens, cost, timings, grader results, diff, and the behaviours observed.
3. **A behaviour catalogue** of failure and success modes, each backed by run ids, so claims link to recorded evidence.
4. **Agent plumbing** (`AGENTS.md`, `CLAUDE.md`, permissions, hooks, named subagents) built from recent, cited industry practice, with bare-versus-plumbed runs that show what the plumbing actually changes.

Everything is open source under the MIT licence. Nothing here asks you to trust a screenshot: each finding points at a run you can inspect.

Status: under construction. Read ARCHITECTURE.md for the design and module owners.

## Principles

- Evidence over opinion. Every claim cites a recorded run or a dated source.
- One everyday, affordable model as the subject: Claude Sonnet 5.5. Cost per run is capped and recorded.
- Graders decide pass or fail. A model's own summary of what it did is data to be checked, never proof.
- Secrets never enter the repository. Runs are redacted before they are committed.
- Every agent has a name and an id, builders and subjects alike, and every one appears in `ledger/agents.jsonl`.
