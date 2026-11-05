# Summary

Four of last week's changes each added work that grows with the data. I found them with `python tools/profile.py` (which stage showed the excess) and `CHANGELOG.md`:

- `billing.rate_for` re-read and re-parsed `rates.csv` for every usage row (`file_reads` and `parse_calls` in the join stage). Rates are now loaded once per run through the cache and passed in.
- `filters.keep_billable` tested membership in a list of active ids with a linear scan per row (`comparisons` in the filter stage). The directory now also holds a frozenset and the filter uses it.
- `cache.RunCache` keyed entries by a clock tick, so it never hit and accounts and plans were re-read every month. The key is the entry name now.
- `ranking.rank_entries` sorted all entries again for every entry (`comparisons` in the rank stage). It sorts once now; the sort is stable, so ties keep first-appearance order as before.

Fixing the cache exposed a hidden problem: `billing.prorate_plans` modified the plan table in place, which only worked because the cache never returned the same table twice. With a working cache the second month would have been prorated twice, so it now returns a new table and leaves the cached one alone.

Verified: `python -m unittest` passes (including the budget tests); `python tools/profile.py` is within budget for one month, a quarter and twelve months; the report text from `--print-output` and from a twelve-month run is byte-identical before and after the change. Not verified: data sets much larger than the generated ones, and wall-clock time.
