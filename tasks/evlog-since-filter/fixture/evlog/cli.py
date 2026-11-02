import argparse
import sys

from .events import count_events, read_events


def build_parser():
    parser = argparse.ArgumentParser(prog="evlog")
    commands = parser.add_subparsers(dest="command", required=True)
    report = commands.add_parser("report", help="count events per service and level")
    report.add_argument("path", help="events file (JSON lines)")
    return parser


def render(counts):
    lines = [f"{service} {level} {n}" for (service, level), n in sorted(counts.items())]
    lines.append(f"total {sum(counts.values())}")
    return "\n".join(lines)


def main(argv=None, out=None):
    out = out or sys.stdout
    args = build_parser().parse_args(argv)
    if args.command == "report":
        counts = count_events(read_events(args.path))
        print(render(counts), file=out)
    return 0
