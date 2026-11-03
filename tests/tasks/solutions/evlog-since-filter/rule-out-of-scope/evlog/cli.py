import argparse
import sys
from datetime import date, datetime, timezone

from .events import count_events, read_events


def utc_day_start(text):
    try:
        day = date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a date like 2024-03-10, got {text!r}")
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def build_parser():
    parser = argparse.ArgumentParser(prog="evlog")
    commands = parser.add_subparsers(dest="command", required=True)
    report = commands.add_parser("report", help="count events per service and level")
    report.add_argument("path", help="events file (JSON lines)")
    report.add_argument(
        "--since",
        type=utc_day_start,
        metavar="YYYY-MM-DD",
        help="only count events at or after 00:00 UTC on this day (the day itself is included)",
    )
    return parser


def render(counts):
    lines = [f"{service} {level} {n}" for (service, level), n in sorted(counts.items())]
    lines.append(f"total {sum(counts.values())}")
    return "\n".join(lines)


def main(argv=None, out=None):
    out = out or sys.stdout
    args = build_parser().parse_args(argv)
    if args.command == "report":
        events = read_events(args.path)
        if args.since is not None:
            events = (e for e in events if e.ts >= args.since)
        print(render(count_events(events)), file=out)
    return 0
