# vaultsnap

A small backup tool: create, list and restore snapshots, and (in progress) prune old ones.

## Retention (old draft, kept for the record)

Early draft from before the ADRs were written: keep the last N snapshots, then one per day, week, month and year, with weeks starting on Sunday and days cut at midnight UTC. Protected tags are never pruned.

The retention rules that apply today are the ones in `docs/adr/`; where this draft differs, the ADRs win.

## Development

    python -m unittest
