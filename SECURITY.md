# Security policy

## Reporting a vulnerability

Report security problems privately. Do not open a public issue, pull request or discussion.

Use GitHub private vulnerability reporting: open the [Security tab](https://github.com/hexrift/agent-black-box/security) and choose **Report a vulnerability**. The report is visible only to the maintainers.

Include what you found, where (file, commit, run id), how to reproduce it, and the impact you expect. If you already know a fix, describe it in the report rather than in a public pull request.

## Scope

In scope:

- The harness in `src/blackbox/`: running tasks, recording the ledger, redaction, grading.
- Graders and fixtures in `tasks/`, including a fixture or grader that could escape the temporary workspace.
- Scripts, the Makefile and CI workflows in `scripts/` and `.github/`.
- The agent plumbing: instruction files, permissions, hooks and subagent definitions.
- Committed data in `runs/` and `ledger/`, including any leaked secret.

Out of scope:

- Behaviour of the subject model itself. An agent that does something unsafe inside a task is a research finding: report it with the behaviour report form.
- Prompt injection planted on purpose in a task fixture. Those traps are deliberate and documented in each task's `NOTES.md`.
- Vulnerabilities in third-party services or dependencies with no path to exploit through this repository. Report those upstream.

## Secret leaks in run data

Run data is redacted before it is committed, and every commit is scanned. A leak is still possible. Treat any of these, found anywhere in the repository or its history, as a secret leak:

- An API key, access token, session token, password or private key, whether live, revoked or partial (a recognisable prefix with enough characters to identify the key).
- The contents of an environment file, or an environment variable dump that includes credentials.
- An authorisation header, cookie or signed URL captured in `events.jsonl`, `diff.patch` or `run.json`.
- Personal data that is not part of the published fixtures, such as an email address or home directory path of a real person.

To report a leak:

1. Do not copy the secret into the report, an issue or a chat. Give the file path, commit, run id and event index (or line number) instead.
2. Report it privately as described above.
3. If the secret is yours, revoke it at its provider first.

The maintainers will revoke or ask for revocation of the credential, remove the data, rewrite history where needed, fix the redactor so the pattern is caught, and add a test for it.

## Response expectations

This project is maintained on a best-effort basis by volunteers.

| Step | Target |
|---|---|
| Acknowledge the report | 3 working days |
| Initial assessment | 7 working days |
| Leaked live credential revoked or removed | as soon as it is confirmed, within 24 hours where possible |
| Fix released for a confirmed vulnerability | 30 days, or a date agreed with the reporter |

Reporters are credited in the advisory unless they ask not to be.

## Supported versions

Only the latest commit on `main` is supported.
