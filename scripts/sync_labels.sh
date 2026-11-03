#!/usr/bin/env bash
set -euo pipefail
repo="${1:-hamsasoftware/agent-black-box}"
while IFS='|' read -r name color description; do
  gh label create "$name" --repo "$repo" --color "$color" --description "$description" --force
done <<'LABELS'
triage|fbca04|Needs a first look from a maintainer
bug|d73a4a|Something is broken
behaviour|5319e7|An observed agent behaviour backed by a run
task-proposal|0e8a16|A proposed challenging task
task|0e8a16|Adds or changes a task
practice|1d76db|A practice for the agent plumbing, with a dated source
plumbing|1d76db|Agent instruction files, permissions, hooks, subagents
harness|c5def5|Runner, ledger, redactor or grading
research|bfdadc|Dated sources and model choice
video|f9d0c4|Replay video
security|b60205|Security or secret handling
documentation|0075ca|Documentation
dependencies|0366d6|Dependency updates
ci|ededed|CI, Makefile or scripts
breaking-change|b60205|Changes a contract others depend on
skip-changelog|ffffff|Leave out of release notes
LABELS
