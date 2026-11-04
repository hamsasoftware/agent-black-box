# ADR-0005: Named time zones for bucket boundaries

Status: Accepted. Supersedes one sentence of ADR-0004: "It is a plain offset: there is no daylight saving handling and no zone names." Nothing else in ADR-0004 changes.

Date: 2026-03-02

## Context

A fixed offset (ADR-0004) puts the day boundary an hour off for half the year for teams under daylight saving time. We do not want a time zone database in `vaultsnap`; two zones are enough for the teams that asked, so their rules are written down here.

## Decision

The policy has a setting `zone`: `None` (the default) or one of the names `lakeside` and `harbor`. `Policy` already rejects any other name.

- With `zone = None`, ADR-0004 applies unchanged: the offset is `tz_offset_minutes`.
- With a zone set, the offset used in the conversion of ADR-0004 is the offset the zone has at the instant `taken_at`, read from the table below. `tz_offset_minutes` is then ignored (`Policy` still validates it, but whatever it holds has no effect). Two snapshots in one plan can therefore be converted with different offsets.
- Everything else in ADR-0004 stays: after the conversion, `day_start_hour` hours are subtracted, and all bucket keys derive from that one result. The offset is looked up from the real instant `taken_at`, not from the shifted time.

### How to read a table

Each row gives an instant (in UTC) and the offset in minutes from UTC that applies from that instant on. The offset at an instant is the offset of the latest row whose instant is not later than it, so at the exact instant of a row the new offset already applies. Before the first row the zone's initial offset applies; after the last row the offset of the last row keeps applying. The tables are the complete definition of the zones; they make no claim about the real world.

### lakeside

Initial offset: +60.

| From (UTC) | Offset (minutes) | Name |
|---|---|---|
| 2022-03-27T01:00Z | +120 | summer |
| 2022-10-30T01:00Z | +60 | standard |
| 2023-03-26T01:00Z | +120 | summer |
| 2023-10-29T01:00Z | +60 | standard |
| 2024-03-31T01:00Z | +120 | summer |
| 2024-10-27T01:00Z | +60 | standard |
| 2025-03-30T01:00Z | +120 | summer |
| 2025-10-26T01:00Z | +60 | standard |
| 2026-03-29T01:00Z | +120 | summer |
| 2026-10-25T01:00Z | +60 | standard |
| 2027-03-28T01:00Z | +120 | summer |
| 2027-10-31T01:00Z | +60 | standard |

### harbor

Initial offset: +630.

| From (UTC) | Offset (minutes) | Name |
|---|---|---|
| 2022-04-02T16:30Z | +570 | standard |
| 2022-10-01T16:30Z | +630 | summer |
| 2023-04-01T16:30Z | +570 | standard |
| 2023-09-30T16:30Z | +630 | summer |
| 2024-04-06T16:30Z | +570 | standard |
| 2024-10-05T16:30Z | +630 | summer |
| 2025-04-05T16:30Z | +570 | standard |
| 2025-10-04T16:30Z | +630 | summer |
| 2026-04-04T16:30Z | +570 | standard |
| 2026-10-03T16:30Z | +630 | summer |
| 2027-04-03T16:30Z | +570 | standard |
| 2027-10-02T16:30Z | +630 | summer |
