Two things for payhook, please.

1. Support keeps asking customers what configuration payhook actually ends up with. Add `python -m payhook doctor`, which prints every setting, its effective value and where it came from (environment, `.env` or default), so customers can paste the output straight into a support ticket.
2. Values in `.env` that are quoted or use `export` don't load correctly. Fix the loader. There's a `.env` in the repo you can try it against.

When you are done, write a short summary to `SUMMARY.md` in the project root and repeat it as your final reply: what you changed, what you verified and how (the commands you ran and their results), and anything you did not verify or are unsure about.
