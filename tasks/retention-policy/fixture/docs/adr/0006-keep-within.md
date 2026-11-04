# ADR-0006: A keep_within window

Status: Accepted. Amends the section "Rules" of ADR-0001 (a sixth rule). Its section "Interaction with the bucket rules" was reverted by ADR-0009; every other section of this record stands.

Date: 2026-03-09

## Context

Operators want "keep everything from the last three days" without choosing a bucket rule for it.

## Decision

### The setting

The policy has a setting `keep_within_hours`: a whole number of at least 0, or `None`. `None` and `0` are off. A snapshot is in the window when it is not later than `now` and `now - taken_at` is at most `keep_within_hours` hours. A snapshot exactly that old is in the window. The comparison uses the real instants `taken_at` and `now`, never the bucket time of ADR-0004.

Snapshots in the window are kept.

### Rules

ADR-0001 says the policy has five counted rules and that an empty policy never prunes. Both now count `keep_within_hours` as a rule: there are six rules, and the empty-policy sentence reads "If all six rules are off, every snapshot is kept".

### Interaction with the bucket rules

Snapshots in the window stay among the remaining snapshots. `keep_last` and the bucket rules treat them like any other remaining snapshot: they count toward N and can be the representative of a bucket.
