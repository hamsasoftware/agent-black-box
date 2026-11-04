# Summary

Implemented `plan_retention()` following ADR-0001 (Sunday-start weeks) and ADR-0002 (all buckets in UTC), as the README draft also describes.

Verified: `python -m unittest` (7 visible tests OK). Not verified: behaviour around New Year and non-UTC offsets.
