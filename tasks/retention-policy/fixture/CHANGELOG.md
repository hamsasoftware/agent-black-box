# Changelog

## Unreleased

- Retention pruning is being added. The rules are decided in docs/adr/ (start with docs/adr/README.md); `plan_retention` in `vaultsnap/retention.py` implements them.
- Weekly buckets are ISO weeks (Monday start) instead of Sunday-start weeks: ADR-0003.
- Bucket boundaries follow the policy settings `tz_offset_minutes` and `day_start_hour` instead of fixed UTC days: ADR-0004. ADR-0002 is retired.
- Policy setting `zone` (`lakeside` or `harbor`) gives the offset with daylight saving from a rule table in the record, instead of a plain `tz_offset_minutes`: ADR-0005.
- Policy setting `keep_within_hours` keeps recent snapshots: ADR-0006. Snapshots in the window used to count toward the other rules; ADR-0009 reverts that part, they are now set aside.
- Incremental snapshots (`Snapshot.parent`): a parent that a kept snapshot depends on is never pruned: ADR-0007.
- Policy setting `expire_tags` prunes scratch snapshots, with a fixed order of overrides: ADR-0008.
- Policy setting `month_start_day` starts monthly buckets on a chosen day: ADR-0010.

## 0.2.0

- `vaultsnap list` shows tags.
- Config files may contain a `retention` section (parsed by `Policy`; not acted on yet).

## 0.1.0

- First release: create and restore snapshots.
