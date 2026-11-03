# Summary

Implemented `satisfies()` and `max_satisfying()` in `depres/ranges.py` by desugaring every form in `docs/RANGES.md` (X-ranges, partial operators, hyphen, tilde, caret including the 0.x cases) into primitive comparators, then applying the prerelease rule per comparator set.

Verified: `python -m unittest` (8 visible tests OK) plus a scratch script covering each row of the tables in the contract and the prerelease examples. Not verified: ranges with build metadata on bounds, and very long `||` chains for performance.
