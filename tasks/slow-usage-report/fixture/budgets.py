"""The budgets of docs/PERFORMANCE.md as code. Do not edit: CI and the profile tool read them from here."""


def budgets(months, usage_rows, account_rows, plan_rows, rate_rows):
    n = usage_rows + account_rows
    return {
        "file_reads": months + 3,
        "parse_calls": usage_rows + account_rows + plan_rows + rate_rows,
        "lookups": 4 * usage_rows + 2 * account_rows * months,
        "comparisons": n * n.bit_length(),
    }
