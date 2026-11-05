import calendar

from .primitives import scan_contains


def days_in_month(month):
    year, number = month.split("-")
    return calendar.monthrange(int(year), int(number))[1]


def keep_billable(rows, directory, days):
    """Rows for active accounts on a real day of the month; everything else is counted as skipped."""
    kept = []
    skipped = 0
    for row in rows:
        if 1 <= row.day <= days and scan_contains(directory.active_ids, row.account_id):
            kept.append(row)
        else:
            skipped += 1
    return kept, skipped
