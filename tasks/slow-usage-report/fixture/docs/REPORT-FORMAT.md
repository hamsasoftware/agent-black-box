# Usage report format

## Inputs

All files are in one data directory and have a header line. Blank lines are ignored, LF and CRLF endings are both accepted.

- `accounts.csv`: `account_id,name,plan_id,status`. Status is `active`, `suspended` or `closed`.
- `plans.csv`: `plan_id,name,included_units,discount_pct`.
- `rates.csv`: `service,price_milli`, the price of one unit in thousandths of a dollar. A service with no rate is free.
- `usage-YYYY-MM.csv`: `account_id,day,service,units`, one file per month.

## Which rows count

A usage row is billable if its account exists, its status is `active` and its day is a real day of that month. Every other row is **skipped** and only counted in the footer. Duplicate rows are not special: each one adds its units.

## Charges

- A month's included units for a plan are `included_units * days_in_month // 30`.
- For an account: `total_units` is the sum of its billable units, `gross` the sum of `units * price_milli`, `overage = max(0, total_units - included)`.
- `billed = gross * overage // total_units * (100 - discount_pct) // 100`, in thousandths of a dollar (0 when `total_units` is 0).
- Money is printed rounded half up to the cent, with thousands separators: `$1,234.56`.

## The report for one month

A title line, a column header, one line per account that has at least one billable row, a footer with the number of accounts, billable rows and skipped rows, and the total charge. Accounts are ranked by billed amount, highest first; accounts with equal amounts keep the order in which they first appear in the usage file. Rank is the position in that order (ties do not share a rank). The top service of an account is the one with the most units; the first one seen wins a tie.

A report for several months is the month reports in the order requested, separated by a blank line, followed by `period total: ... over K months`.
