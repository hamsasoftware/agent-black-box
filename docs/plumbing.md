# Agent plumbing

What each plumbing file does, the practice it implements, the sources behind it (ids from [sources.json](sources.json), summarised in [best-practices.md](best-practices.md)), and what the evidence cannot show.

The evidence on instruction files is mixed. One study found faster runs and fewer output tokens with an `AGENTS.md` (S004), another found no gain in success and over 20% more cost (S003), and a third found no correctness effect (S005). The only factorial study found no effect of file size or structure on adherence (S006). So every file here is kept short, rules with no exceptions are enforced by permissions and hooks rather than prose, and the effect of the bundle is measured rather than assumed (see the last section).

## This repository

| File | Practice | Sources | What the evidence cannot show |
|---|---|---|---|
| `AGENTS.md` | One shared instruction file: exact commands first, always / ask first / never tiers, a runnable definition of done, a security rule, nothing the code already says | S001, S002, S011, S010, S009, S007, S057 | Whether it raises success at all (S003 versus S004, S005); the tiers come from a descriptive review, not a controlled test |
| `CLAUDE.md` | Thin adapter that imports `AGENTS.md`, plus tool-specific notes only | S001, S009, S012 | Whether one tool's import resolves exactly like another tool reading `AGENTS.md` directly |
| `CLAUDE.local.md` (git-ignored, not committed) | Personal instructions kept out of the shared contract | S009, S010 | Nothing measured |
| `.claude/settings.json` | Deny secrets paths, piping downloads to a shell, destructive git, merging, and edits to `runs/` and `ledger/`; ask before real runs, pushes, installs, deletes and changes to agent configuration; allow only the routine commands | S026, S050, S034, S088, S048, S049 | Command-text patterns miss reordered flags, wrappers and subprocesses (S026); without an OS sandbox (S027) a determined process can still read a denied file |
| `.claude/hooks/guard.py` and `command_policy.py` | PreToolUse hook that parses each shell command and blocks what it does with secrets files and protected paths, fails closed on unreadable input, and explains the block (exit code 2) | S028, S026, S010, S090 | See "Limits of command guards" below; it cannot see what a script it allows does once running |
| `.claude/hooks/log_tool_call.py` | PostToolUse hook that appends one redacted JSON line per tool call to `.claude/logs/tool-calls.jsonl` (git-ignored) | S042, S043, S060, S062 | Redaction is pattern-based and can miss unknown secret formats; it records inputs and response sizes, not full outputs |
| `.claude/hooks/stop_reminder.py` | Stop hook: if the session edited files, block the first stop once and restate the definition of done | S010, S056, S097, S098 | Whether a reminder changes behaviour; S065 and S058 disagree on whether asking works, and it costs one extra turn |
| `.claude/agents/*.md` | One named subagent per builder with a when-to-use description and a minimal tool allowlist; `atlas` reads untrusted web pages and so gets no edit or shell tools | S019, S010, S017, S037, S044 | Multi-agent value for coding is disputed (S017, S018); no turn cap is set in the definitions |

## Experiment variants

The harness copies one of these into each task workspace. Nothing in them names this project or the experiment.

| File | Practice | Sources | What the evidence cannot show |
|---|---|---|---|
| `plumbing/variants/bare/` | Control: no instruction file, no settings, no hooks | S059 | — |
| `plumbing/variants/plumbed/AGENTS.md` (32 lines) | Verify before claiming and say what was not verified; flag ambiguity; do not edit tests; treat file content as untrusted; stay in scope; stop and report when blocked | S010, S098, S097, S058, S044, S030, S086, S099, S088 | Prompting against cheating has mixed results (S065, S058, S077); adherence falls as a session generates more code (S006) |
| `plumbing/variants/plumbed/CLAUDE.md` | One line importing `AGENTS.md` so the subject tool reads it | S009, S001 | — |
| `plumbing/variants/plumbed/.claude/settings.json` | Deny rules only: secrets, download-to-shell, push, destructive git, skipped hooks | S026, S048 | Grants nothing; the harness must apply the same allow rules and permission mode to both variants |
| `plumbing/variants/plumbed/.claude/hooks/guard.py` and `command_policy.py` | One small guard hook using the same command parser as the repository guard (the two `command_policy.py` copies are kept identical by a test) | S028, S026 | See "Limits of command guards" below |

Tests are left writable on purpose. Making them read-only would block the most common cheat (S058) but would also hide whether the instruction changes behaviour, which is what the experiment measures. The hidden graders check test edits instead.

## Guard change after INC-016

The first guard matched the text `.env` anywhere in a command, so it blocked commands that only named the file: `git check-ignore .env`, `git ls-files .env`, and a heredoc writing a summary that mentioned `.env`. Three plumbed runs of one task hit these blocks and had to retry (INC-016 in `docs/incidents.md`).

Both guards now parse the command and decide by what each simple command does with a path:

- Reads are blocked: any command given a secrets path as an argument or input redirect (`cat`, `head`, `grep` file arguments, `sed`, `awk`, `cp`, `base64`, `xxd`, `source`, `curl -d @.env`, `git show HEAD:.env` and others), code passed to an interpreter that opens a secrets path or loads it with a dotenv helper, and anything that prints the environment (`printenv`, `env` with no command, `set`, `export -p`, `os.environ`, `process.env`).
- Naming is allowed: `git check-ignore`, `git ls-files`, `git status`, `git log`, `git commit` messages, `git diff --stat`, existence checks (`ls`, `test`, `[`), `find` without an action, the pattern argument of `grep`, `echo` and `printf` text, comments, and heredoc bodies written by `cat` or `tee`. Heredoc bodies fed to a shell or an interpreter are still checked, and so are substitutions inside unquoted heredocs.
- Commands, `$(...)`, backquotes, `sh -c`, `eval` and `xargs` are analysed recursively. A command that cannot be parsed is blocked.

The real commands from the three runs are kept as allowed cases in `tests/plumbing/test_secret_names.py`, next to over 50 real secret reads that must stay blocked, for both guards.

## Limits of command guards

A guard that reads command text cannot see everything the command does (S026):

- A script or program it allows can open any file once running: `python3 tool.py`, `make`, a test runner, or a package's install hook.
- Indirection through variables (`f=.env; cat "$f"`), file lists built at run time (`find ... | xargs cat`, globs that expand to `.env`), and recursive searches (`grep -r TOKEN .`) are not resolved.
- Interpreter code is checked for common read calls only; an unusual API or computed path passes.
- Name rules are a fixed list (`.env` and `.env.*` except examples, key and credential files, `~/.ssh`, `~/.aws`, `/proc/*/environ`); any other file holding a secret is not recognised.

The permission deny rules and an OS sandbox (S027) are the backstop; the guard is a fast first check that should rarely fire on harmless work.

## How the effect is measured

Each task runs several times per variant (S059), on the same model, caps and fixture (ADR 0002). The harness compares bare and plumbed runs on:

- grader pass rate and score, reported as pass@k and pass^k;
- test files edited or special-cased (graders and diff);
- claims in the final message that the grader or tooling did not confirm (`claims` versus `verified_claims`);
- injected instructions followed, out-of-scope files changed, and stops that reported a block;
- turns, tokens, cache tokens and cost, since S003 found instruction files raise cost;
- guard blocks and permission denials.

The plumbed variant changes three things at once (instruction file, deny rules, guard hook), so a difference measures the bundle, including any friction the guard adds, not the effect of any one part. Separating them would need more variants. With few trials per task and run-to-run variance of up to 30 times in tokens (S025), small differences should be read as noise.
