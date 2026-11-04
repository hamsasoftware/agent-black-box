# ADR-0003: Weekly buckets are ISO weeks

Status: Accepted. Supersedes the section "Weeks" of ADR-0001.

Date: 2026-02-09

## Context

Sunday-start weeks (ADR-0001) disagree with the calendars and reports our users already read, which use ISO 8601 weeks. Around New Year the two also put the same snapshots in different weeks.

## Decision

The weekly bucket key is the ISO calendar pair (ISO year, ISO week number), as `date.isocalendar()` returns it; weeks start on Monday. Buckets are ordered by that pair, so (2026, 1) is newer than (2025, 52).

The ISO year is used only for weekly buckets. Monthly buckets stay (calendar year, calendar month) and yearly buckets stay the calendar year. For example, a snapshot dated 2025-12-30 is in weekly bucket (2026, 1), monthly bucket (2025, 12) and yearly bucket 2025.

Nothing else in ADR-0001 changes.
