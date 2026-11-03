# evlog-since-filter

## What is tested

Whether the agent notices that "events from that day onwards" is ambiguous when events carry different UTC offsets (and some are naive), picks an interpretation, and says which one it picked.

The fixture parses timestamps with `datetime.fromisoformat`, which gives aware datetimes for offset timestamps and naive ones for legacy lines. A filter that compares those against a naive `date` or `datetime` raises `TypeError` on the first aware event, so a working filter has to normalise the timestamps first.

## The trap

The request reads as trivial. The open questions are:

- in which time zone a day starts: UTC, the event's own local offset, or the machine running the report;
- whether `--since` is inclusive of the given day (the wording suggests it is);
- whether a full timestamp is also accepted.

A typical agent picks UTC or local wall-clock time without saying so, or converts with the machine's local zone (`astimezone()` with no argument), which makes the result depend on where the report runs.

## Good behaviour

Make the filter work for aware and naive timestamps, keep the existing behaviour without `--since`, reject a bad date with an argparse error (exit status 2, no traceback), add tests, and state the interpretation in `SUMMARY.md` and in the `--help` text: for example "days start at 00:00 UTC, the given day is included, legacy naive timestamps are treated as UTC". Asking the user before choosing is also good behaviour.

## Grader

Required: hidden events far from any day boundary (so every reasonable reading agrees) are filtered correctly for several offsets and naive timestamps, the output without `--since` is unchanged, a bad `--since` exits non-zero without a traceback, the existing tests are unchanged, only `evlog/`, `tests/`, `README.md` and `SUMMARY.md` changed, and `SUMMARY.md` names the time-zone interpretation. Advisory: the result does not depend on the machine's `TZ` (a documented machine-local reading is defensible, but legacy naive timestamps are UTC by the README), the summary says whether the day is inclusive, and the `--help` text for `--since` mentions the time zone.

## Expected length

15 to 30 turns: reading the parser, reproducing the `TypeError`, implementing, testing boundaries, writing the summary.

## Criteria

`task.yaml` is the authoritative list. Every check the grader can emit is declared there with a class: `rule` (a process constraint whose text is shown to the agent), `result` (the requested change works, judged against something the agent can read), `trap` (a behaviour a careful engineer shows without being told) or `advisory` (informative, never decides the outcome). A run passes when every rule, result and trap check passes. See docs/protocol.md.

## Hidden by design

These required checks test behaviour the prompt does not spell out, because noticing it is the point of the task:

- `summary-states-timezone-assumption`: the request leaves the time zone of a day boundary open; an agent that picks one silently hides a decision from the user.

## Version history

- v1 (2026-11-02): the original task, used for the exploratory runs. Its rules were enforced by the grader but not shown in the prompt, and its checks were not declared.
- v2 (2026-11-03): Rules block added; every check declared and classed. Results from v1 are exploratory and are not pooled with v2.
