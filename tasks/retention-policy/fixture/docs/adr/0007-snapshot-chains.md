# ADR-0007: Incremental snapshots depend on their parent

Status: Accepted. Adds a final step after the rules of ADR-0001; supersedes nothing.

Date: 2026-03-16

## Context

A snapshot can now be incremental: it stores only what changed since its parent snapshot and cannot be restored without it. Pruning a parent that a kept snapshot still needs would destroy the kept snapshot.

## Decision

### Parents

`Snapshot.parent` is the id of the snapshot it depends on, or `None` for a full snapshot. The parent is another snapshot of the same plan; it may have been taken at any time, earlier or later than the child.

Two more cases raise `ValueError`, like the naive datetimes and duplicate ids of ADR-0001: a `parent` that is not the id of any snapshot in the plan, and a cycle of parents (a snapshot that is its own parent is a cycle). They are raised whatever the policy is.

### The dependency step

All other decisions are made first, exactly as if no snapshot had a parent. Then one step is added at the very end: every snapshot that is the parent of a kept snapshot is kept too, and so on up the chain until nothing changes. Such a snapshot is called held.

- Only kept snapshots hold their parents. A snapshot that ends up pruned holds nothing.
- A held snapshot does not count toward `keep_last`, toward any bucket rule's N or toward `keep_within_hours`, and it is never the representative of a bucket: the rules never see the step. It only adds snapshots to the result.
- The step cannot make a snapshot pruned, and it comes after every other mechanism, so it also overrides the ones that mark a snapshot for pruning (see ADR-0008).
