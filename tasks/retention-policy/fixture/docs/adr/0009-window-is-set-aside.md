# ADR-0009: Window snapshots are set aside

Status: Accepted. Reverts the section "Interaction with the bucket rules" of ADR-0006; nothing else in ADR-0006 changes. Adds the window to the list of overrides in ADR-0008.

Date: 2026-03-30

## Context

With the interaction ADR-0006 chose, a window of seven days used up seven slots of `keep_daily = 7` on the same snapshots, so nothing older than the window was ever kept by the daily rule. Operators expected the bucket rules to start where the window ends.

## Decision

Snapshots in the window (as ADR-0006 defines it) are set aside, like protected ones: always kept, not counted toward `keep_last` or any bucket rule's N, and never the representative of a bucket. The bucket rules and `keep_last` look only at the remaining snapshots, which now exclude the window.

In the list of overrides of ADR-0008 the window is a new line 4, after expired snapshots and before the remaining snapshots:

1. protected: kept; 2. later than `now`: kept; 3. expired: pruned; 4. in the window: kept, set aside; 5. every other snapshot is among the remaining snapshots.

So an expired snapshot inside the window is pruned (unless line 1 or 2 applies or the dependency step of ADR-0007 holds it).
