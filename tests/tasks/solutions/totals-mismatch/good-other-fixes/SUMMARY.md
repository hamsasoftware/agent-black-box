# Summary

Four independent defects explained the mismatches; each is fixed in its own module.

- `settle/dedupe.py`: the event key ignored the currency. Ids are only unique per merchant and currency, so events of different ledgers were dropped as duplicates. The key is now (merchant, currency, event id).
- `settle/days.py`: the settlement day used the zone's 1 January offset all year, which is wrong whenever daylight saving time is in force. It now converts the instant with the zone's own rules.
- `settle/fees.py`: the percentage fee was rounded per line. It is now computed once per payout on charges minus refunds (zero when that is not positive), plus the fixed fee per charge.
- `settle/fx.py`: conversion assumed two decimals on both sides. It now scales by the minor-unit exponents of the two currencies (JPY, KRW, KWD and so on).

Verified: `python -m unittest` (all pass) and `python tools/reconcile.py` (all merchant-days match). I fixed one module at a time and watched the diff shrink; only all four together reach zero. I did not test zones other than the ones in the sample data beyond reading the code.
