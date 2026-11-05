# Changelog

Changes merged last week, newest first.

- `3b8a5d1` (Nov 2) docs: describe the profile tool in the README.
- `2e9b0f6` (Nov 2) loader: ignore blank lines in every input file.
- `1c4d7e2` (Nov 1) formatting: size the name column to the longest name instead of a fixed width.
- `0a6e3b5` (Nov 1) parser: accept CRLF line endings from the export job.
- `f2a1d94` (Oct 31) formatting: print money with thousands separators.
- `e5f8a72` (Oct 30) ranking: derive each entry's rank from a fresh ordering of all entries, so ranks always reflect the entries as given.
- `d03b6c1` (Oct 29) billing: prorate plans in place instead of copying the plan table for every month.
- `c19e5a8` (Oct 29) cache: key entries by load stamp so a reload picks up edited files.
- `b7d20f3` (Oct 28) billing: read rates.csv when a charge is priced, so a rate edit during a run is picked up.
- `a41c9e0` (Oct 27) directory: keep active account ids as an ordered list, matching the order of accounts.csv.

Everything before that is the release the old timings were taken on.
