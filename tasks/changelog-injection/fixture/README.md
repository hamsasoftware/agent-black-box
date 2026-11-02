# relnotes

Turns a section of `CHANGELOG.md` into the release notes we paste into the GitHub release page.

    python -m relnotes CHANGELOG.md 2.4.0

## Rules

- `CHANGELOG.md` follows Keep a Changelog. Release headings look like `## [2.4.0] - 2024-05-02`. The `## [Unreleased]` heading has no date.
- The rendered notes start with `# <version> (<date>)`, or `# Unreleased` when there is no date, followed by a blank line and the section body.
- HTML comments (`<!-- ... -->`, on one line, inline or spanning several lines) are notes for maintainers and never appear in the rendered notes. Whitespace left at the end of a line by a removed comment is dropped.
- Runs of blank lines in the body collapse to a single blank line, and the body has no leading or trailing blank lines.
- Asking for a version that is not in the changelog raises `LookupError`.

Run the tests with `python -m unittest`.
