"""Run the report on generated data and print the operation counters per stage next to the budgets.

    python tools/profile.py [--accounts N] [--rows N] [--months K] [--seed S] [--print-output]

The counters tell you where work is being done, not why. With --print-output the report text is printed
instead, so two runs can be compared byte for byte.
"""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from budgets import budgets  # noqa: E402
from tools.gen_data import generate, month_names  # noqa: E402
from usage_report import counters  # noqa: E402
from usage_report.parser import data_lines  # noqa: E402
from usage_report.report import build_period  # noqa: E402

STAGES = ["load", "parse", "filter", "join", "aggregate", "rank", "format"]
NAMES = ["file_reads", "parse_calls", "lookups", "comparisons", "cache_hits", "cache_misses"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--accounts", type=int, default=150)
    ap.add_argument("--rows", type=int, default=1200, help="usage rows per month")
    ap.add_argument("--months", type=int, default=3)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--print-output", action="store_true")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        months = month_names(args.months)
        generate(tmp, args.seed, args.accounts, args.rows, months)
        counters.reset()
        text = build_period(tmp, months)
        if args.print_output:
            sys.stdout.write(text)
            return
        size = lambda name: len(data_lines((Path(tmp) / name).read_text()))
        rows = sum(size(f"usage-{m}.csv") for m in months)
        limit = budgets(len(months), rows, size("accounts.csv"), size("plans.csv"), size("rates.csv"))
    per_stage = counters.by_stage()
    print(f"{'stage':<10}" + "".join(f"{n:>14}" for n in NAMES))
    for stage in STAGES:
        print(f"{stage:<10}" + "".join(f"{per_stage.get(stage, {}).get(n, 0):>14}" for n in NAMES))
    total = counters.totals()
    print(f"{'total':<10}" + "".join(f"{total.get(n, 0):>14}" for n in NAMES))
    print(f"{'budget':<10}" + "".join(f"{limit[n]:>14}" if n in limit else f"{'':>14}" for n in NAMES))
    over = [n for n in limit if total.get(n, 0) > limit[n]]
    print("within budget" if not over else "OVER BUDGET: " + ", ".join(over))


if __name__ == "__main__":
    main()
