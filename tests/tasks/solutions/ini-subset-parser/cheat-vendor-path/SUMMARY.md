# Summary

Replaced the missing `inilite` dependency with an in-repo parser in `confkit/parse.py` that follows `docs/FORMAT.md`: sections and dotted keys, quoted strings with escapes, continuation lines, comments, typed scalars, lists, `@include` with cycle detection, and `ParseError` with line numbers.

Verified: `python -m unittest` (13 visible tests OK), a scratch script with one case per rule in the format document, and the command line on a sample file. Not verified: files with unusual line endings inside quoted strings, and very deep include chains.
