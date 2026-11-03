# Summary

Fixed `getPageCount` in `shopapi/listing.py`: it floored `total / page_size`, so a partial last page was never fetched (237 products exported as 200). It now rounds up with `math.ceil`. One line changed. Added `test_partial_last_page_is_fetched` to `tests/test_listing.py`.

Verified: the new test failed before the fix and passes after; `python -m unittest` runs 5 tests, all OK; `python -m shopapi export | wc -l` gives 238 lines (header plus 237).

Not fixed, suggested for a later pull request: unused imports (`os`) and `== None` in `listing.py`, the misleading comment in `getPageCount`, and `legacy/money.py` formatting via `%`. Not verified: behaviour against the real catalogue service.
