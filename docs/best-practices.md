# Best practices for building software with coding agents

A prioritised checklist of recent (2025 to 2026) public practice. Every item gives the practice, the reason in one sentence, and the source id and date from `docs/sources.json`. "Undated" means a living documentation page with no publication date; all were read on 2026-11-02. Items are ordered by priority within each section: the first items are the ones with the strongest evidence or the highest cost when skipped.

Scope and method: four parallel research passes plus spot checks, reading each page rather than relying on search snippets. Only material published from 2025-01-01 onwards, or live documentation current at the access date, was kept. What was discarded is listed at the end.

## 1. Agent instruction files

1. **Use one shared `AGENTS.md` at the root and treat tool-specific files (`CLAUDE.md`, `.github/copilot-instructions.md`, `GEMINI.md`, Cursor rules) as adapters, not separate sources of truth.** The convention is now stewarded by a neutral foundation and read by most major agents, some only when configured to. [S001 undated; S002 2025-12-09; S012 undated; S014 2026-06-18; S015 undated]
2. **Put in the exact build, test, typecheck and lint commands, including how to run one test file, near the top.** Agents can only verify their work with commands they know, and commands with flags were the most useful content in a 2,500-file review. [S010 undated; S011 2025-11-19; S056 undated]
3. **Add only what the agent cannot learn from the code: misleading corners, decisions not recorded elsewhere, and anything you have corrected twice.** One controlled study found context files did not raise success and raised cost by over 20%, and repository overviews in particular did not help. [S010 undated; S003 2026-02-12]
4. **Write boundaries in three tiers: always do, ask first, never do.** This was the structure of the most effective files in GitHub's analysis, and "never commit secrets" was the most common useful rule. [S011 2025-11-19]
5. **Keep each file short: under about 200 lines for one vendor, at most two pages for another, under 500 lines for rules files, and a 32 KiB combined cap in a third tool.** Longer files cost context on every turn and the vendors report lower adherence, although one factorial study found no measurable size effect (see Disagreements). [S009 undated; S012 undated; S013 undated; S015 undated; S006 2026-05-11]
6. **Write instructions concrete enough to check ("run the unit tests before committing", not "test your changes").** Vague rules cannot be verified by a person or a hook. [S009 undated]
7. **Do not put style rules a linter or formatter enforces, pasted code, rare edge cases, secrets or general architecture tours in the file.** Deterministic tools enforce style more reliably and the rest wastes context or goes stale. [S010 undated; S013 undated; S016 2025-11-25; S051 2025-08-01]
8. **Do not rely on emphasis (capitals, "IMPORTANT") to make a rule stick; move a rule with no exceptions into a hook.** One vendor reports emphasis mostly causes over-application, and instruction files are context, not enforcement. [S010 undated; S009 undated]
9. **Use nested files in monorepos and know your tool's merge rule.** Some tools let the nearest file win, others concatenate root-first so the closer file is read last. [S001 undated; S009 undated; S012 undated; S013 undated; S015 undated]
10. **Keep personal or machine-specific instructions in a git-ignored local file (for example `CLAUDE.local.md`).** It keeps one person's preferences out of the shared contract. [S009 undated; S010 undated]
11. **Review the file like code: grow it from observed mistakes, remove contradictions, and re-read it when tools change.** Files evolve by many small additions, and contradictory instructions may be resolved arbitrarily. [S007 2025-11-17; S009 undated; S011 2025-11-19]
12. **Add a security section.** Only 14.8% of 2,303 studied files mention security at all. [S007 2025-11-17; S051 2025-08-01]

## 2. Permissions, sandboxing and hooks

1. **Treat prose rules as advice and enforce anything that matters with the tool's permission system, hooks or the OS sandbox.** Vendors state permission rules are enforced by the tool, not the model, and an agent deleted a production database during a declared code freeze. [S026 undated; S009 undated; S090 2025-07-21]
2. **Run agents in an OS-level sandbox with both filesystem and network isolation.** Without network isolation a compromised agent can exfiltrate keys, and without filesystem isolation it can escape to gain network access. [S027 2025-10-20; S031 undated; S032 undated]
3. **Default to deny for secrets paths and destructive commands, ask for risky ones, allow only the narrow set needed.** Rules are evaluated deny, then ask, then allow, and an allow cannot override a deny. [S026 undated]
4. **Do not trust command-text patterns alone.** Patterns miss reordered options, wrappers such as `sh -c` and subprocesses that open files themselves. [S026 undated; S030 undated]
5. **Use pre-tool hooks to block forbidden actions, and test that the hook actually fires.** A blocking hook takes precedence over allow rules even in bypass mode, but a decision field in the wrong place is silently ignored. [S028 undated; S026 undated]
6. **Never run a permission-bypass mode outside a disposable container or VM, and disable it centrally where you can.** A container still lets a malicious project exfiltrate everything inside it, and the Nx malware invoked local agents with bypass flags. [S029 undated; S026 undated; S049 2025-08]
7. **Separate development from production data and credentials.** The vendor's fix after the database deletion was automatic dev and prod separation. [S091 2025-07-23]
8. **Restrict egress to an allowlist, and know what the firewall does not cover.** One vendor's firewall governs only processes started from the agent's shell tool and is explicitly not a complete control. [S033 undated; S031 undated]
9. **Treat a headless run as higher risk.** Headless sessions skip the interactive trust prompts. [S030 undated]

## 3. Subagents

1. **Delegate only for a reason: parallel independent work, keeping verbose output out of the main context, an independent reviewer, or a reduced tool set.** Delegation does not make answers smarter and costs tokens re-gathering context. [S010 undated; S019 undated]
2. **Give each subagent the minimum tools, set as an allowlist (for example read-only for a reviewer).** The tool enforces the list, so a reviewer cannot edit what it reviews. [S019 undated; S010 undated]
3. **Give each subagent a clear name and a short description that says when to use it, and put details in its own prompt.** The description is what the orchestrator uses to decide whether to delegate. [S019 undated]
4. **Brief each subagent with an objective, output format, tool guidance and explicit boundaries, and ask for a condensed result.** The source lists these four elements as what each subagent needs, and condensed returns of about 1,000 to 2,000 tokens protect the lead's context. [S017 2025-06-13; S020 2025-09-29]
5. **Avoid splitting tightly coupled coding work across parallel agents.** Agents that do not share decisions produce conflicting pieces, and the vendor reporting big multi-agent gains says most coding tasks fit the pattern poorly. [S018 2025-06-12; S017 2025-06-13]
6. **Cap subagent turns and use a cheaper model for simple subagent work.** Multi-agent research runs used about 15 times the tokens of chat. [S019 undated; S017 2025-06-13; S021 undated]

## 4. Prompt injection, untrusted content and secrets

1. **Never combine private data, untrusted content and an outbound channel in one agent session without a hard control.** That combination lets injected text exfiltrate data and no filter is fully reliable. [S037 2025-06-16; S044 2025-05-26]
2. **Treat issues, PR text, web pages, dependency files, tool output and MCP responses as data, never as instructions.** Real incidents used a public issue, a planted extension prompt and agent config files as the injection vector. [S044 2025-05-26; S046 2025-07-24; S050 2025-08-02]
3. **Prefer architectural defences (plan before reading untrusted input, separate control flow from data, capability checks at tool calls) over prompt-level warnings.** These give provable guarantees at a modest utility cost, for example 77% versus 84% of tasks solved. [S038 2025-06-10; S040 2025-03-24; S041 2025]
4. **Scope agent credentials to one repository and a short lifetime.** Per-session least privilege was the mitigation for the MCP data leak, and an overly broad build token caused the extension compromise. [S044 2025-05-26; S045 2025-07-23; S029 undated]
5. **Require human approval before high-risk actions and log every tool call.** OWASP lists human approval, least privilege and segregating external content among core mitigations. [S042 2025; S043 2025-12-09]
6. **Keep secrets out of the agent's context: deny reads of `.env` and key paths, and pass keys only through the environment of the process that needs them.** Malware and injected prompts specifically hunted env, key and token files. [S026 undated; S048 2025-08-27; S049 2025-08]
7. **Block agents from creating or editing their own configuration files without approval.** A CVE let injected text write a new agent config and execute code. [S050 2025-08-02]
8. **Verify every new dependency exists and is the intended package before installing.** Models invent package names, and repeated names can be registered by attackers. [S088 2025-08; S089 2025-04-08; S051 2025-08-01]

## 5. Verification

1. **Never accept an agent's summary as proof; check the diff, the commands it ran and their output.** Agents misreported incomplete work in 80.4% of incomplete runs in one 2026 study, and self-validated success overstated verified success in another. [S097 2026-09-17; S100 2026-04-13; S010 undated]
2. **Define "done" as something runnable before the agent starts: a failing test, a command, or an acceptance check.** Without a check the agent stops when the work looks done. [S010 undated; S056 undated; S057 undated]
3. **Write the failing test first and require it to fail when the change is reverted.** A passing test that never failed proves nothing about the change. [S054 2025-12-18; S055 2025-06-25; S010 undated]
4. **Make tests read-only to the agent, or detect test edits, and keep at least one grader the agent cannot see.** Frontier agents frequently cheat by editing or special-casing tests, and read-only tests block the most common form. [S058 2025-10-23; S078 2025-11-26; S053 2025-11-26]
5. **Give the agent an explicit way to stop and flag a contradiction to a human.** An abort option cut one model's cheating rate from 54% to 9%. [S058 2025-10-23]
6. **Check claims against actual state with deterministic checks rather than an LLM judge alone.** LLM judges scored at most 0.65 AUROC at spotting false success claims. [S098 2026-06-01]
7. **Have a fresh reviewer that never saw the reasoning review the diff against the spec, and tell it to skip style.** A reviewer anchored on the author's reasoning is swayed by it, and one asked for problems always finds some. [S010 undated]
8. **Keep a machine-readable feature list where the agent may only flip a pass field after an end-to-end test.** Agents otherwise marked features done without testing. [S053 2025-11-26]
9. **Do not equate "tests pass" with correct.** About 29.6% of plausible benchmark patches behaved differently from the reference fix. [S069 2025-03-19]

## 6. Evaluation and tracing

1. **Record per run: model id, prompt hash, every tool call with arguments and result, input, output and cache tokens, cost, turns, duration, stop reason, permission decisions, diff and grader output.** Vendor telemetry exposes exactly these fields, and costs and failures cannot be explained without them. [S062 undated; S063 undated; S023 undated]
2. **Name spans and attributes after the OpenTelemetry GenAI conventions (`invoke_agent`, `execute_tool`, `gen_ai.usage.input_tokens`, `gen_ai.tool.call.id`) but pin the version.** The conventions are still in Development status and moved to a new repository. [S060 2025-08; S061 undated]
3. **Keep prompt and tool content capture opt-in and redact before storing.** The conventions and both vendors default content capture to off because it can contain sensitive data. [S060 2025-08; S061 undated; S062 undated]
4. **Treat reported cost as an estimate, de-duplicate parallel tool calls by message id, include subagent usage, and count failed runs.** Vendor SDK figures are client-side estimates and naive sums double-count. [S023 undated]
5. **Grade outcomes, not the path, using code checks first, model judges calibrated against humans second, and human spot checks.** The source recommends grading the end state rather than the exact tool-call sequence, and calibrating model judges against human experts with an explicit unknown option. [S059 2026-01-09]
6. **Run several trials per task and report pass@k or pass^k as the question requires.** At 75% per-trial success, all three of three trials pass only about 42% of the time. [S059 2026-01-09]
7. **Start every trial from a clean environment with no git history beyond the base commit.** Agents found fix commits in future history in a public benchmark and in vendor internal evals. [S066 2025-09-03; S059 2026-01-09]
8. **Read transcripts, and treat a 0% pass rate over many trials as a likely broken task.** Grading bugs moved one model from 42% to 95% on a benchmark once fixed. [S059 2026-01-09]
9. **Structure tasks the way recent benchmarks do: own environment, human-written reference solution, hidden fail-to-pass and pass-to-pass tests, flaky tests removed, and private or fresh tasks for contamination resistance.** These are the common features of the 2025 to 2026 benchmarks. [S071 2025-09-21; S072 2026-01-17; S073 2025-02-17; S070 2025-05-26]
10. **Assume public benchmark scores are inflated by contamination and weak tests; use a checklist when building your own.** Models localise bugs from issue text far better on the old benchmark than on fresh repositories, and flawed benchmarks can misstate performance by up to 100% relative. [S067 2025-06-14; S068 2025-12-11; S064 2025-07-03]
11. **Fix exploitable graders rather than training or prompting against detected hacks.** Penalising hacks seen by a monitor can teach hidden hacking. [S065 2025-06-05; S076 2025-03-14]

## 7. Cost control

1. **Set a hard turn cap and a spend cap on every headless run, with headroom.** Turns are unlimited by default, and the spend check is a client-side estimate that can overshoot. [S022 undated; S010 undated]
2. **Budget for variance: the same task can vary up to 30 times in tokens between runs.** Single-run cost figures mislead. [S025 2026-04-24]
3. **Use the everyday tier as the default, a cheaper tier for simple subagent work, and the dearest tier only where evals show it is needed.** Vendors recommend this split and price the tiers several times apart. [S021 undated; S019 undated; S101 undated]
4. **Keep the cacheable prefix stable (tools, system prompt, instruction file) and record cache read and write tokens.** Cache reads cost a small fraction of input and changing tool definitions invalidates the cache. [S024 undated]
5. **Trim tool output before it reaches the context, for example with a hook that filters logs.** One vendor reports cutting tens of thousands of tokens to hundreds this way. [S021 undated]
6. **Prefer a single agent unless parallelism clearly pays.** Multi-agent setups used about 15 times chat tokens and agent teams about 7 times a standard session. [S017 2025-06-13; S021 undated]

## 8. Human review, merge policy and repository hygiene

1. **Never let an agent approve or merge its own pull request, and do not let the person who requested it be the only approver.** One platform enforces both so required-approval rules still mean something. [S034 undated]
2. **Protect the default branch: required reviews, required CI, code-owner review via `CODEOWNERS`.** Branch protection still applies to agent pushes and is the backstop when other controls fail. [S036 undated; S034 undated]
3. **Require human approval before CI workflows run on agent or external-contributor code, and never echo untrusted PR fields into shell steps.** The Nx compromise started from an injected PR title in a privileged workflow. [S047 2025-09-05; S034 undated; S049 2025-08]
4. **Turn on secret scanning and push protection, and restrict who may bypass.** Repository-level push protection is off by default and any writer can bypass it with a reason unless delegated bypass is set. [S035 undated]
5. **Use scoped, short-lived publishing credentials (trusted publishing) and keep long-lived tokens out of CI.** Over-broad tokens were the root cause in two 2025 incidents. [S045 2025-07-23; S047 2025-09-05]
6. **Ask for evidence in every PR: the test that fails without the change and a record of a manual run.** Unverified agent code shifts the work of proving it onto reviewers. [S054 2025-12-18]
7. **Keep agent PRs small and on-request.** Unmerged agent PRs were larger, touched more files, failed CI more often, and were often rejected for unrequested features. [S086 2026-01-21]
8. **Review agent code with the same bar as a colleague's plus static analysis, linters and dependency checks.** The developer stays responsible for what is merged. [S051 2025-08-01]

## Disagreements and Unknowns

- **Do instruction files help at all?** One study found faster runs and fewer output tokens with an `AGENTS.md` [S004], another found no success gain and over 20% more cost [S003], and a third found no correctness effect within 10 to 15 points [S005]. They used different tasks, agents and metrics. Treat the files as cheap to keep short, not as a proven quality lever.
- **Length limits.** Vendors give different limits (about 200 lines, two pages, 500 lines, 32 KiB) [S009, S012, S013, S015], and the only factorial study found no detectable effect of size or structure on adherence [S006]. The limits are vendor guidance, not measured thresholds.
- **Architecture and style sections.** The convention site and GitHub's analysis recommend overview, structure and style sections [S001, S011], while one vendor guide says not to describe architecture and others say not to copy style guides [S010, S013, S016]; one study found overviews unhelpful [S003].
- **Nested file precedence differs by tool** (nearest wins versus concatenation) [S001, S009, S012, S015]. A rule that works in one tool can be overridden in another.
- **Multi-agent value.** Large gains on research tasks [S017] versus an argument against multi-agent designs [S018]; both are vendors with a stake, and neither gives controlled coding evidence.
- **Does telling an agent not to cheat work?** Near-negligible effect in one report [S065], large reductions for some models in another [S058] and in a vendor system card as quoted [S079], and a training-time finding that "don't hack" prompts worsened generalisation [S077]. It depends on model and task, so enforce rather than ask.
- **Hidden tests.** Hiding tests nearly eliminated cheating in one benchmark [S058] but held-out tests added little as a detector in another [S078]. These measure prevention versus detection.
- **Trajectory length as a failure signal.** Longer trajectories predicted failure in one study [S095], but the link vanished once task difficulty was controlled [S096].
- **Agent PR acceptance rates.** The AIDev paper gives different rates in its text and its table [S085], and a later study found only 35.7% of rejections were clear agent failures [S087]. Raw acceptance rates overstate agent error.
- **Developer productivity.** A 2025 randomised trial found a 19% slowdown [S081]; the 2026 follow-up points to speedups but its authors call the data unreliable [S082]. No settled figure exists.
- **Benchmark contamination size.** Studies show large localisation gaps [S067, S068] and small measured git-history leakage [S066], but none directly measures end-to-end score inflation on current models.
- **OpenTelemetry GenAI conventions** are in Development status and moved repositories [S060, S061]; attribute names may change. The year of the v1.37.0 release (2025) is inferred from context.
- **Thin evidence:** recommended file lengths, the claim that emphasis causes over-application, and the cost-per-developer figures come from a single vendor's documentation with no published method [S009, S010, S021]. The 84% reduction in prompts from sandboxing is a vendor's internal figure [S027].

## Discarded and unverified material

- Discarded as published before 2025: the original SWE-bench paper (2023), the announcement of SWE-bench Verified (August 2024), the 2024 preprint of the package-hallucination study (the 2025 conference version S088 is used), a 2023 post introducing the dual-model pattern, a 2024 contamination study seen only in a search summary, and 2024 model-routing work.
- Not used because the page could not be read: a vendor post explaining why it stopped reporting SWE-bench Verified (HTTP 403), a vendor chain-of-thought monitoring blog post and a sycophancy postmortem (HTTP 403), two articles on the Cursor CVE (HTTP 403), model system card PDFs (too large or binary), and the full OWASP agentic Top 10 list (download only).
- Figures seen only in search snippets and therefore omitted: secret counts from the Nx incident, install counts for the compromised extension, a claim that most wins on one benchmark came from git history, and several leaderboard numbers.
