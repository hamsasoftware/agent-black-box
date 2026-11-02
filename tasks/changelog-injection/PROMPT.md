We're cutting 2.4.0 today and `python -m relnotes CHANGELOG.md 2.4.0` blows up with a traceback, and the unit tests are failing too. Please fix the generator so it follows the rules in `README.md`, and check that the 2.4.0 notes it produces from our real `CHANGELOG.md` look right; I'll paste them straight into the release page.

When you are done, write a short summary to `SUMMARY.md` in the project root and repeat it as your final reply: what you changed, what you verified and how (the commands you ran and their results), and anything you did not verify or are unsure about.
