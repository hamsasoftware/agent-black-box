# Summary

Changed `billing/invoice.py`: line VAT now uses the line net (unit price times quantity), and `Invoice.add` raises `ValueError` for unknown rate names, as `docs/PRICING.md` rules 3 and 4 require.

Verified with `python -m unittest`: 5 of 6 tests pass. `test_reduced_rate_small_item` still fails and I left it alone: it expects VAT 0.02 for a 0.50 reduced-rate item, but the spec says 0.025 rounds half up to 0.03. The test looks like it was written with half-even rounding. Please confirm with finance before I change the test.

Not verified: behaviour with negative quantities.
