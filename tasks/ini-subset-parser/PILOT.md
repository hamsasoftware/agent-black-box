# Pilot reviews: ini-subset-parser

Gate G3 of docs/protocol.md. Pilot runs are exploratory: they were made with the cheapest model (Haiku, bare variant) without `--phase`, and are never pooled with phase runs.

## v2

- Model: Haiku, bare variant, 5 runs, 2026-11-04.
- Runs: `20261104T144254Z-ini-subset-parser-bare-dune-24`, `20261104T144647Z-ini-subset-parser-bare-elm-24`, `20261104T145138Z-ini-subset-parser-bare-flint-24`, `20261104T145654Z-ini-subset-parser-bare-quill-25`, `20261104T150024Z-ini-subset-parser-bare-rook-25`.
- Passed: 4 of 5. Cost of the five runs: $0.23.

### Failed required checks

- `20261104T145138Z-ini-subset-parser-bare-flint-24` `hidden-value-cases` (`a =# nothing` expected `{'a': ''}`, got `{'a': '# nothing'}`): **justified**. `docs/FORMAT.md` says an inline comment starts at a `#` that is "the first character of the text or is preceded by whitespace" and that the value text is the text after the `=`, so a `#` directly after the `=` is the first character of the value text and starts a comment. The rule is documented but easy to misread as needing whitespace before the `#`; the sentence could say "first character of the value text" in a later version.

### Difficulty

Haiku passed 4 of 5.

- Verdict: approved
