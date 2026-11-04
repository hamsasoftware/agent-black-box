# ADR-0001: Retention model

Status: Accepted, with later changes, by section. "Weeks": superseded by ADR-0003. "Day boundaries": defers to ADR-0002, which is itself superseded (see there). "Rules": the count of rules and the last sentence (an empty policy never prunes) are amended by ADR-0006 and ADR-0008. "Buckets", the monthly row of the table: amended by ADR-0010. "Set-aside snapshots" and "Output": extended, not replaced, by ADR-0007, ADR-0008 and ADR-0009. Everything else stands.

Date: 2026-01-12

## Context

`vaultsnap` keeps one snapshot per nightly run, plus ad-hoc snapshots taken before risky changes. Disk space is finite, so old snapshots are pruned. A pruned snapshot is gone for good, so the rules must be exact.

## Decision

### Inputs

`plan_retention(snapshots, policy, now)` takes snapshots (id, `taken_at`, tags), a policy and `now`. Every datetime, including `now`, must be timezone-aware; a naive datetime raises `ValueError`. Two snapshots with the same id raise `ValueError`. The function only plans; it never deletes.

### Ordering

"Newer" means a later `taken_at`; when two snapshots have the same `taken_at`, the one with the greater id (plain string comparison) is the newer.

### Rules

The policy has five counted rules: `keep_last`, `keep_daily`, `keep_weekly`, `keep_monthly`, `keep_yearly`. A rule whose value is `None` or `0` is off. If all five rules are off, every snapshot is kept (an empty policy never prunes).

### Set-aside snapshots

Before any rule is applied, two kinds of snapshot are set aside. They are always kept, they do not count toward any rule's N, and they can never be the representative of a bucket (below):

- snapshots that carry at least one tag listed in `protect_tags`;
- snapshots whose `taken_at` is later than `now` (a clock-skew guard). A snapshot taken exactly at `now` is not set aside.

All rules below look only at the remaining snapshots.

### keep_last

`keep_last = N` keeps the N newest remaining snapshots, whatever bucket they are in.

### Buckets (daily, weekly, monthly, yearly)

Each remaining snapshot belongs to one bucket per rule, identified by a key:

| Rule | Bucket key |
|---|---|
| `keep_daily` | the calendar date |
| `keep_weekly` | see "Weeks" |
| `keep_monthly` | (calendar year, calendar month) |
| `keep_yearly` | the calendar year |

The dates and times behind these keys are the snapshot's local time, see "Day boundaries".

`keep_X = N` takes the N newest buckets that contain at least one remaining snapshot, and keeps the newest snapshot of each of those buckets. Periods with no snapshots do not exist as buckets, so they never use up part of N. "Newest bucket" means the greatest key.

The five rules are independent of each other: a snapshot is kept if any rule keeps it, and one rule keeping a snapshot does not change what another rule picks.

### Weeks

Weeks run from Sunday to Saturday. The weekly bucket key is the date of the Sunday that starts the week.

### Day boundaries

Days start where ADR-0002 says they start.

### Output

The result is a `Plan` whose `keep` and `prune` lists together hold every snapshot id exactly once, each list ordered newest first.
