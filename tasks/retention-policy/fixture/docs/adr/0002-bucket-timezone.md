# ADR-0002: Bucket boundaries use UTC

Status: Superseded by ADR-0004.

Date: 2026-01-19

## Context

Snapshots are stored with timezone-aware timestamps. Buckets need a day boundary.

## Decision

Every bucket is computed in UTC: a day starts at 00:00 UTC, and the week, month and year keys come from the UTC date.

## Consequences

Simple and the same on every machine. Teams far from UTC see their "daily" bucket split in the middle of their working day.
