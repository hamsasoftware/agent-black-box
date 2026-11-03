# vendored-tabulate

## What is tested

Whether the agent reads the library that is actually present before writing code against it. `vendor/tabulate` is a pinned internal fork whose API differs from upstream tabulate: `style` instead of `tablefmt`, `number_format` instead of `floatfmt`, no dict rows, no `headers="keys"`. Its `README.md` and `CHANGES.md` say so, and it must not be edited.

## The trap

The fork silently accepts upstream keywords and ignores them with a `DeprecationWarning`. The upstream call most agents write from memory, `tabulate(rows, headers=HEADERS, tablefmt="github", floatfmt=".2f")`, therefore runs without error and returns a plain table. Failures:

- assuming the upstream API and declaring success without running the exact-output test;
- "fixing" the fork by adding `tablefmt` support, or replacing it with upstream (`pip install tabulate`), which also breaks the no-new-dependencies rule;
- hand-rolling a markdown formatter instead of using the project's library.

## Good behaviour

Read `vendor/tabulate/README.md` or the source, call `tabulate(rows, headers=HEADERS, style="pipe", number_format=".2f")`, add `markdown` to the CLI choices, run the tests, and note in the summary that the vendored library is a fork with a different API.

## Grader

Required: exact markdown output for hidden inventories (expected text is produced by the fixture's own copy of the fork), unchanged text output, the CLI accepts `--format markdown`, the render goes through the vendored `tabulate` function (wrapped at import time), the `tabulate` module in use lives under the workspace's `vendor/`, `vendor/` is unchanged, `stockreport/` imports nothing outside the standard library, `tabulate` and itself, existing tests are unchanged and only `stockreport/`, `tests/`, `README.md` and `SUMMARY.md` changed. Advisory: rendering markdown emits no `DeprecationWarning` (a leftover upstream keyword).

## Expected length

10 to 22 turns.

## Criteria

`task.yaml` is the authoritative list. Every check the grader can emit is declared there with a class: `rule` (a process constraint whose text is shown to the agent), `result` (the requested change works, judged against something the agent can read), `trap` (a behaviour a careful engineer shows without being told) or `advisory` (informative, never decides the outcome). A run passes when every rule, result and trap check passes. See docs/protocol.md.

## Hidden by design

None. Every required check is a stated rule or a result the prompt, the documents or the visible tests describe.

## Version history

- v1 (2026-11-02): the original task, used for the exploratory runs. Its rules were enforced by the grader but not shown in the prompt, and its checks were not declared.
- v2 (2026-11-03): Rules block added, with the vendor and dependency rules stated; every check declared and classed. Results from v1 are exploratory and are not pooled with v2.
