# ADR-0004: Configurable day boundary

Status: Accepted. Supersedes ADR-0002.

Date: 2026-02-23

## Context

ADR-0002 fixed buckets to UTC. Our nightly job runs at 01:30 to 03:30 local time, so with a UTC day the "daily" bucket put a night's snapshot together with the previous evening's ad-hoc snapshots for some teams and not for others.

## Decision

The policy has two settings that decide where a day starts:

- `tz_offset_minutes`: a fixed offset from UTC in minutes (default 0). It is a plain offset: there is no daylight saving handling and no zone names.
- `day_start_hour`: the local hour at which a day starts, 0 to 23 (default 0).

The bucket time of a snapshot is computed as follows: convert `taken_at` to the fixed offset, then subtract `day_start_hour` hours. The calendar date of the result is the snapshot's date, and the daily, weekly (ADR-0003), monthly and yearly keys are all derived from that one result. So with `day_start_hour = 4`, a snapshot taken at 03:30 local on 1 January belongs to 31 December of the previous year in every rule.

Only the bucket keys use the bucket time. Ordering of snapshots, `keep_last`, and the comparison with `now` use the real instant `taken_at` and are not shifted.

With the defaults (offset 0, hour 0) this is the UTC behaviour of ADR-0002.
