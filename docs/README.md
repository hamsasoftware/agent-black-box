# Documentation

Every document in this repository, what it is for and who should read it. Documents marked *planned* are being written and will be linked when they land.

## Start here

| Document | What it is | For |
|---|---|---|
| [README](../README.md) | What the project is, its principles and where to go next | Everyone |
| [CONTRIBUTING](../CONTRIBUTING.md) | Quickstart, branch and commit rules, adding a task, proposing a practice | Contributors |
| [Navigation proposal](navigation-proposal.md) | Draft "Start here" section for the README | Maintainers |

## How it works

| Document | What it is | For |
|---|---|---|
| [ARCHITECTURE](../ARCHITECTURE.md) | Modules and owners, task format, run ledger fields, safety rules | Contributors, reviewers |
| `docs/ledger.md` *(planned)* | How the harness records, redacts and grades a run | Anyone reading run data |
| [Model choice](model-choice.md) | Which subject model is used and why | Researchers |
| [Agent plumbing](plumbing.md) | Each plumbing file, the practice it implements, its sources and limits, and how its effect is measured | Practitioners, researchers |
| [Incident log](incidents.md) | Every error found while building or running the repo: who introduced it, who found it, impact, fix and lesson | Everyone, especially anyone adding an agent or a detector |
| [Architecture decisions](adr/) | Short records of why the setup is the way it is | Reviewers, future maintainers |
| [ADR 0002](adr/0002-subject-model-run-caps-and-redaction.md) | One subject model, run caps, redaction before commit | Researchers, reviewers |

## Evidence

| Document | What it is | For |
|---|---|---|
| [Best practices](best-practices.md) | Dated, cited industry practice for agent instruction files, permissions, hooks and subagents | Practitioners |
| [What trips agents](what-trips-agents.md) | Documented failure modes with evidence and trap ideas | Task authors, researchers |
| [sources.json](sources.json) | Machine-readable list of every source, with URL and date | Researchers, tooling |
| `behaviour/taxonomy.yaml` *(planned)* | The behaviour ids used in run records and issue forms | Researchers, task authors |
| `runs/` *(generated)* | One directory per recorded run: `run.json`, `events.jsonl`, `diff.patch`, `grade.json` | Anyone checking a claim |
| `docs/video.md` *(planned)* | How the replay video is built from run data | Viewers, video contributors |

## Contributing

| Document | What it is | For |
|---|---|---|
| [CONTRIBUTING](../CONTRIBUTING.md) | How to contribute, step by step | Contributors |
| [Pull request template](../.github/PULL_REQUEST_TEMPLATE.md) | What every pull request must state | Contributors |
| [Task pull request template](../.github/PULL_REQUEST_TEMPLATE/task.md) | Extra checks for a new task | Task authors |
| [Issue forms](../.github/ISSUE_TEMPLATE/) | Bug, behaviour report, task proposal, practice suggestion | Everyone |
| [SECURITY](../SECURITY.md) | Reporting vulnerabilities and leaked secrets privately | Everyone |
| [Code of Conduct](../CODE_OF_CONDUCT.md) | Expected behaviour in project spaces | Everyone |
| [ADR 0001](adr/0001-record-architecture-decisions.md) | How decisions are recorded | Maintainers |
| [ADR 0003](adr/0003-ci-action-pinning-and-code-owners.md) | CI action pins and code owners | Maintainers |
