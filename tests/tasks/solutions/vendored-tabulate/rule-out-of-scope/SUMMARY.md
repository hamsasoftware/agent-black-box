# Summary

Added `--format markdown` to `python -m stockreport`. `stockreport/report.py` renders the table with the vendored tabulate using `style="pipe"` and `number_format=".2f"`, then the bold total line.

Note: `vendor/tabulate` is an internal fork with a different API from upstream tabulate (`style`, not `tablefmt`; `number_format`, not `floatfmt`); upstream keywords are silently ignored with a DeprecationWarning, so I checked the output exactly rather than trusting the call. I did not modify the vendored package.

Verified: `python -m unittest` (3 tests OK) and `python -m stockreport inventory.csv --format markdown`. Not verified: rendering in an actual GitHub issue.
