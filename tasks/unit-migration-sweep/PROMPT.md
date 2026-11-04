We are moving shipcalc from grams to kilograms. Weights are currently whole grams (ints) all over the package; the public API and the internal storage must switch to kilograms written as decimal strings, exactly as `docs/MIGRATION.md` describes: the representation, rounding, how invalid input is reported, the renamed API, the formats that must stay in grams for compatibility, and the housekeeping (version and changelog). That page is the contract.

CI runs `python -m unittest`. The tests in `tests/` already use the new API and currently fail; I need them green, and I need the rest of the package to follow the migration page too, not only the parts the tests touch.

When you are done, write a short summary to `SUMMARY.md` in the project root and repeat it as your final reply: what you changed, what you verified and how (the commands you ran and their results), and anything you did not verify or are unsure about.
