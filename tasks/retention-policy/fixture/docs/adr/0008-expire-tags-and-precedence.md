# ADR-0008: Expire tags and the order of overrides

Status: Accepted. Amends the last sentence of the section "Rules" of ADR-0001 (the empty policy), as already amended by ADR-0006. Extends the section "Set-aside snapshots" of ADR-0001. The position of the window in the list of overrides below was added by ADR-0009.

Date: 2026-03-23

## Context

Scratch snapshots (taken before a risky change and worthless afterwards) should be pruned even when a rule would have kept them, and we need an explicit order for what wins when a snapshot matches several tag or time conditions.

## Decision

The policy has a setting `expire_tags`, a set of tags like `protect_tags`. A snapshot that carries at least one tag listed in `expire_tags` is called expired.

### Order of overrides

For each snapshot the first line of this list that applies decides, from the top:

1. It carries a tag listed in `protect_tags`: kept, set aside (ADR-0001).
2. Its `taken_at` is later than `now`: kept, set aside (ADR-0001).
3. It is expired: pruned. It is excluded from all rules; like a set-aside snapshot it does not count toward any N and is never a representative.
4. Every other snapshot is among the remaining snapshots, to which the rules apply.

The dependency step of ADR-0007 comes after this list and overrides line 3: an expired snapshot that is the parent of a kept snapshot is kept. It changes nothing for lines 1 and 2.

A tag may be listed in both `protect_tags` and `expire_tags`; line 1 then wins.

### Empty policy

When none of the six rules is on, the rules decide nothing and every snapshot is kept, except that expired snapshots are still pruned under the order above (they are kept when line 1 or 2 applies, or by the dependency step).
