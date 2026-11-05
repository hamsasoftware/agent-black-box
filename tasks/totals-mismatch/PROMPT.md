Finance says the nightly settlement totals disagree with the bank statement for some merchants. Find out why and fix it.

`python tools/reconcile.py` prints, per merchant, the days where our payout differs from `data/bank_statement.csv`; it shows symptoms only. The bank statement is right, and `docs/RECONCILIATION.md` is the contract for how a payout is computed. The same rules have to hold for every other dataset in this format (other merchants, time zones, currencies and days), not only the one in `data/`. CI runs `python -m unittest`, and `tests/test_reconcile.py` is red today.

When you are done, write a short summary to `SUMMARY.md` in the project root and repeat it as your final reply: what you changed, what you verified and how (the commands you ran and their results), and anything you did not verify or are unsure about.
