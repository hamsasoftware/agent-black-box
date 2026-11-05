"""Deterministic synthetic data for the profile tool and the budget tests."""
import calendar
import random
from pathlib import Path

PLANS = [("free", "Free", 100, 0), ("team", "Team", 1000, 5), ("business", "Business", 5000, 10), ("scale", "Scale", 20000, 15)]
RATES = [("api_calls", 2), ("storage_gb", 40), ("egress_gb", 90), ("build_minutes", 15), ("seats", 500), ("support_hours", 0)]
SERVICES = [name for name, _ in RATES] + ["legacy_sms"]  # legacy_sms has no rate: free
FIRST = ["Aldermoor", "Brightwater", "Calder", "Dunmore", "Eastgate", "Fenwick", "Garrow", "Highfold", "Ironbridge", "Juniper"]
SECOND = ["Freight", "Labs", "Analytics", "Foods", "Works", "Media", "Energy", "Systems", "Textiles", "Health"]


def month_names(count, start_year=2026, start_month=1):
    names = []
    for i in range(count):
        index = start_month - 1 + i
        names.append(f"{start_year + index // 12}-{index % 12 + 1:02d}")
    return names


def generate(directory, seed, accounts, rows_per_month, months, ties=False):
    rng = random.Random(seed)
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    (root / "plans.csv").write_text("plan_id,name,included_units,discount_pct\n" + "".join(f"{a},{b},{c},{d}\n" for a, b, c, d in PLANS))
    (root / "rates.csv").write_text("service,price_milli\n" + "".join(f"{a},{b}\n" for a, b in RATES))
    ids, lines = [], []
    for i in range(1, accounts + 1):
        account_id = f"acct-{i:04d}"
        ids.append(account_id)
        name = f"{FIRST[rng.randrange(len(FIRST))]} {SECOND[rng.randrange(len(SECOND))]} {i}"
        plan = PLANS[rng.randrange(len(PLANS))][0]
        roll = rng.randrange(100)
        status = "active" if roll < 85 else ("suspended" if roll < 93 else "closed")
        lines.append(f"{account_id},{name},{plan},{status}\n")
    rng.shuffle(lines)
    (root / "accounts.csv").write_text("account_id,name,plan_id,status\n" + "".join(lines))
    for month in months:
        days = calendar.monthrange(*map(int, month.split("-")))[1]
        out = ["account_id,day,service,units\n"]
        for _ in range(rows_per_month):
            if rng.randrange(100) < 4:
                account_id = f"acct-9{rng.randrange(1000):03d}"  # not in accounts.csv
            else:
                account_id = ids[rng.randrange(len(ids))]
            day = rng.randrange(1, 32) if rng.randrange(100) < 5 else rng.randrange(1, days + 1)
            service = SERVICES[rng.randrange(len(SERVICES))]
            units = rng.randrange(0, 4) * 50 if ties else rng.randrange(0, 400)
            out.append(f"{account_id},{day},{service},{units}\n")
            if rng.randrange(100) < 3:
                out.append("\n")
        (root / f"usage-{month}.csv").write_text("".join(out))
    return root
