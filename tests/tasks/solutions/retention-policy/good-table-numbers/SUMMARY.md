# Summary

Implemented `plan_retention()` in `vaultsnap/retention.py`.

| Part | ADR | Why |
|---|---|---|
| Model: set-aside snapshots, keep_last, independent bucket rules, empty policy keeps everything, output order | 0001 | The base decision record |
| Weekly buckets are ISO weeks (ISO year used for weeks only) | 0003 | Supersedes the "Weeks" section of ADR 0001 |
| Bucket keys come from `taken_at` converted to `tz_offset_minutes` and shifted back by `day_start_hour`; `keep_last` and the future check use the real instant | 0004 | Supersedes 0002 (UTC days) |

Verified: `python -m unittest` (7 visible tests OK) and a scratch script for the New Year and day-start cases. Not verified: very large snapshot lists.
