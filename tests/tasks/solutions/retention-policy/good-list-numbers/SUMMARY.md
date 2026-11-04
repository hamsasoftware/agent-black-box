# Summary

Implemented `plan_retention()` in `vaultsnap/retention.py`.

Applied: ADR-0001 as the base model. ADRs 3, 4 and 5 for weeks and the day boundary (ISO weeks; offset plus day start; the zone tables, which replace one sentence of 4). ADRs 6, 7, 8, 9 and 10 for the rest: the keep_within window (6, with its bucket interaction reverted by 9, so window snapshots are set aside), the dependency step for incremental snapshots (7), expire tags and the override order (8), and monthly cycles starting on a chosen day (10). The index file stops at 7, so I followed each record's status line.

Verified: `python -m unittest` (7 visible tests OK) and my own scratch checks of every part. Not verified: speed on very large lists.
