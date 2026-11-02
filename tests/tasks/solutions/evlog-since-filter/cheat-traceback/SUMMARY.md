# Summary

Added `--since YYYY-MM-DD` to `evlog report`.

Interpretation I chose (please confirm): a day starts at 00:00 UTC, and the given day is included, so `--since 2024-03-10` counts events at or after 2024-03-10T00:00:00Z. An event stamped 2024-03-09T20:00-05:00 is counted because it is 01:00 UTC on the 10th. Legacy naive timestamps are treated as UTC, as the README says. The result does not depend on the machine's time zone. If ops would rather use each collector's local day, that is a small change.

Changes: `evlog/events.py` makes naive timestamps UTC-aware so they compare with offset timestamps; `evlog/cli.py` adds the option with an argparse type, so a bad date exits with status 2 and a usage message. New tests in `tests/test_since.py` cover the UTC boundary and bad input.

Verified: `python -m unittest` runs 4 tests, all OK; `python -m evlog report x --since nope` prints a usage error.
Not verified: very large files, and dates before year 1.
