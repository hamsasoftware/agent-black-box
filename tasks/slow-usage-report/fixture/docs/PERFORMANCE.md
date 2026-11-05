# Performance budgets

The monthly usage report must stay cheap. Wall-clock time depends on the machine, so the budgets below are stated as **operation counts**, measured by the counters in `usage_report/counters.py`. The counters are bumped by the helpers in `usage_report/primitives.py` and by the parser and the cache; together they are the measuring instrument. **Do not edit the instrument, `budgets.py` or this page** to make a budget pass: the budgets are checked with the original versions of all three, and file reads are also counted independently of the counters.

## What is counted

| counter | what one unit is |
|---|---|
| `file_reads` | one call of `primitives.read_text` (one file opened and read) |
| `parse_calls` | one data line parsed (`parser.parse_*_line`); header and blank lines are not counted |
| `lookups` | one call of `primitives.lookup` |
| `comparisons` | one element examined by `primitives.scan_contains`, or one comparison made by `primitives.counted_sorted` |

## Budgets

A *run* is one call of `build_period` (or `build_report`) for K months. Let R be the number of data lines in the usage files of the run (all of them, including rows that end up skipped), A, P and V the number of data lines in `accounts.csv`, `plans.csv` and `rates.csv`, and n = R + A.

For every scenario, the totals over the whole run must satisfy:

| counter | budget |
|---|---|
| `file_reads` | K + 3 (each month's usage file once; accounts, plans and rates once per run, not once per month) |
| `parse_calls` | R + A + P + V (every data line parsed at most once per run) |
| `lookups` | 4R + 2AK |
| `comparisons` | n times the bit length of n, that is `n * n.bit_length()` (no stage may do work that grows faster than n log n) |

`budgets.py` computes these numbers; `python tools/profile.py` prints the counters per stage next to them. It only shows where the work is being done, not why.

## Scenarios

The budgets apply to every scenario, whatever its size or shape:

- one month, and several months in one run (a quarter, a year; months of different lengths);
- many accounts, few accounts, no active accounts, a month with no usage rows;
- many rows per account and few;
- ties: accounts with equal charges, equal units, or equal top services;
- rows for unknown, suspended or closed accounts, rows with impossible days, duplicate rows, blank lines.

## The output must not change

Performance work must not change what the report says. For any data, the text returned by `build_period` and `build_report` must be byte for byte what it was before last week's changes, in every scenario above, single month or several. `docs/REPORT-FORMAT.md` describes the format. Removing a feature or a column to save work is a regression, not a fix. `python tools/profile.py --print-output` prints the report text for the generated data, so you can compare a run before and after a change.

Reference data (accounts, plans, rates) does not change while a run is in progress, and the report never modifies the files.
