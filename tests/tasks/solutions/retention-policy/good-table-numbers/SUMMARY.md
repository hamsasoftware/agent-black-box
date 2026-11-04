# Summary

Implemented `plan_retention()` in `vaultsnap/retention.py`.

| Part | ADR | Why |
|---|---|---|
| Model: set-aside snapshots, keep_last, independent bucket rules, output order | 0001 | The base decision record |
| Weekly buckets are ISO weeks (ISO year used for weeks only) | 0003 | Supersedes the "Weeks" section of ADR 0001 |
| Bucket keys from `taken_at` converted to the offset and shifted back by `day_start_hour` | 0004 | Supersedes 0002 (UTC days) |
| Zone table lookup at the real instant, `tz_offset_minutes` ignored when a zone is set | 0005 | Replaces one sentence of 0004 |
| `keep_within_hours` is an inclusive window | 0006 | Its bucket-interaction section is reverted |
| Window snapshots are set aside | 0009 | Reverts part of 0006 |
| Ancestors of kept snapshots are held, counting toward nothing | 0007 | Final step |
| `expire_tags` and the order of overrides | 0008 | Protect, future, expire, window (0009), remaining |
| `month_start_day` cycles | 0010 | Leap years and short months |

Verified: `python -m unittest` (7 visible tests OK) and a scratch script for the cases above. Not verified: very large snapshot lists. The index in docs/adr/README.md is behind (it stops at 0007), so I read the status lines.
