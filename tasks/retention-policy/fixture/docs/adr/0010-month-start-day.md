# ADR-0010: Monthly buckets can start on a chosen day

Status: Accepted. Amends the row `keep_monthly` of the table in the section "Buckets" of ADR-0001; nothing else in ADR-0001 changes.

Date: 2026-04-06

## Context

Some teams report by billing cycle, from the 15th to the 14th. Short months and leap years need a rule.

## Decision

The policy has a setting `month_start_day`, a whole number from 1 to 31 (default 1). It affects the monthly bucket key only; daily, weekly and yearly keys do not change.

Take the snapshot's date after ADR-0004's conversion and shift (and ADR-0005's zone, when set). For a month with `last` days (28 or 29 for February, 30 or 31 for the others), the cycle of that month starts on day `min(month_start_day, last)` of that month and runs until the day before the next month's cycle starts. The monthly key is (year, month) of the cycle the date falls in, so a date before its own calendar month's start belongs to the previous month's cycle (January's previous month is December of the previous year). Keys are ordered by that pair, newest greatest.

The yearly key is still the calendar year of the date. With `month_start_day = 15`, 2026-01-10 is in monthly bucket (2025, 12) and yearly bucket 2026.

February has 29 days in a leap year and 28 otherwise; the Gregorian rule applies (a year divisible by 4 is a leap year, except years divisible by 100 that are not divisible by 400). Examples with `month_start_day = 31`: the cycle of February 2028 starts on 29 February, that of February 2027 on 28 February, that of April on 30 April. So 2028-02-28 is in the cycle (2028, 1) and 2028-02-29 in (2028, 2); 2027-02-28 is in (2027, 2) and 2027-03-30 in (2027, 2) while 2027-03-31 is in (2027, 3).

With the default 1 the key is (calendar year, calendar month), as before.
