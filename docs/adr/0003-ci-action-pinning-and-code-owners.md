# 3. Pin CI actions by commit and route reviews to the maintainer

Date: 2026-11-02

Status: Accepted

## Context

Tags on third-party GitHub Actions can be moved, so a workflow that references `@v7` runs whatever code the tag points to today. GitHub's security hardening guide recommends pinning actions to a full commit SHA. Workflow files are code and carry no explanatory comments in this repository, so the human-readable version of each pin has to live somewhere else.

The module owners in ARCHITECTURE.md are builder agents, not GitHub accounts, so CODEOWNERS cannot name them.

## Decision

Every action in `.github/workflows/` is pinned to a full commit SHA. The workflow sets `permissions: contents: read` at the top level, and checkout does not persist credentials. Dependabot updates the pins weekly. This table is the record of what each SHA is, and is updated with every pin change.

| Action | Version | Commit SHA | Released | Verified |
|---|---|---|---|---|
| actions/checkout | v7.0.1 | 3d3c42e5aac5ba805825da76410c181273ba90b1 | 2026-07-20 | 2026-11-02 |
| actions/setup-python | v7.1.0 | 6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 | 2026-10-22 | 2026-11-02 |
| lycheeverse/lychee-action | v2.9.0 | e7477775783ea5526144ba13e8db5eec57747ce8 | 2026-07-09 | 2026-11-02 |
| trufflesecurity/trufflehog | v3.99.2 | e76dff8a7e57d6df0c60ad8cbf5d5cba505a8fc9 | 2026-10-08 | 2026-11-02 |

Each SHA was resolved from the release tag through the GitHub API, dereferencing annotated tags to their commit. These were the latest releases of the newest major version on the verification date, except TruffleHog, where a release at least two weeks old was chosen over one published that day.

CODEOWNERS maps every path in the module table to the maintainer account, `@hexrift`, which reviews all builder pull requests. The per-module lines are kept so that a module can be handed to a human owner by changing one line.

## Consequences

- A moved or compromised tag cannot change what CI runs without a reviewed pull request.
- Pins go stale without Dependabot. Dependabot pull requests that bump a pin must also update this table.
- Every pull request requests review from the maintainer, regardless of module.
