# Summary

Implemented `plan_retention()` per ADR-0001, ADR-0003 and ADR-0004. Protected snapshots are kept and also serve as bucket representatives, and snapshots after `now` are treated like any other.

Verified: `python -m unittest` (7 visible tests OK). Not verified: edge cases.
