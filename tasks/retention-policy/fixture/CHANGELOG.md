# Changelog

## Unreleased

- Retention pruning is being added. The rules are decided in docs/adr/; `plan_retention` in `vaultsnap/retention.py` implements them.
- Weekly buckets are ISO weeks (Monday start) instead of Sunday-start weeks: ADR-0003.
- Bucket boundaries follow the policy settings `tz_offset_minutes` and `day_start_hour` instead of fixed UTC days: ADR-0004. ADR-0002 is retired.

## 0.2.0

- `vaultsnap list` shows tags.
- Config files may contain a `retention` section (parsed by `Policy`; not acted on yet).

## 0.1.0

- First release: create and restore snapshots.
