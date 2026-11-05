# Summary

Fixed the event key in `settle/dedupe.py`, the settlement day in `settle/days.py` and the fee rounding in `settle/fees.py`. The diff in `tools/reconcile.py` shrank a lot after each change. I ran the unit tests. I did not verify the remaining merchants with Japanese yen or Kuwaiti dinar events; they probably come from stale rates.
