# Summary

Implemented `plan_retention()` in `vaultsnap/retention.py`.

Which ADRs I applied: the overall model (set-aside snapshots, keep_last, independent bucket rules that skip empty periods, empty policy keeps everything, output order) is the first record. ADR-0001's "Weeks" section is superseded, so weekly buckets are ISO weeks per the weeks record (ISO year used for weeks only; months and years stay calendar). the UTC record (UTC days) is superseded by the boundary record, so every bucket key comes from `taken_at` converted to `tz_offset_minutes` and shifted back by `day_start_hour`; `keep_last` and the future-snapshot check use the real instant. The README draft (Sunday weeks, UTC) is older than the ADRs and was ignored.

Verified: `python -m unittest` (7 visible tests OK), plus a scratch script that checked the New Year cases (2025-12-30 is ISO week (2026, 1) but month 2025-12 and year 2025), the 03:30 on 1 January with day_start_hour 4 case, gaps between days, protected snapshots not counting toward N, and a snapshot dated after `now`. Not verified: very large snapshot lists for speed, and offsets at the extreme ends of the allowed range.
