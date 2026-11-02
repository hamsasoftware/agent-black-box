# evlog

Small command-line tool the ops team uses to summarise event logs exported from our collectors.

    python -m evlog report events.jsonl

prints one line per service and level with the number of events, then a total.

Each line of an events file is a JSON object:

    {"ts": "2024-03-09T23:30:00-05:00", "service": "api", "level": "error", "msg": "upstream timeout"}

Collectors run in several regions and stamp events with their own UTC offset. Legacy collectors (anything installed before 2024) write naive timestamps such as `2024-03-09 22:10:00`; those are UTC. Blank lines are ignored.

Run the tests with `python -m unittest`.
