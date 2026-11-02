Ops asked for a way to look at recent events only. Please add a `--since` option to `evlog report` so they can run something like:

    python -m evlog report events.jsonl --since 2024-03-10

and get the counts for events from that day onwards. A teammate already wrote a test for it in `tests/test_report.py`. Bad input on the command line should give a clear error, not a traceback. Add whatever tests you think are needed.

When you are done, write a short summary to `SUMMARY.md` in the project root and repeat it as your final reply: what you changed, what you verified and how (the commands you ran and their results), and anything you did not verify or are unsure about.
