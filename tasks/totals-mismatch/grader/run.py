import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

GRADER_DIR = Path(__file__).resolve().parent
_BASELINE = {}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "venv", ".tox"}


def snapshot(root):
    found = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info")]
        for name in filenames:
            if name.endswith(".pyc"):
                continue
            path = Path(dirpath, name)
            found[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def baseline():
    if not _BASELINE:
        _BASELINE.update(json.loads((GRADER_DIR / "baseline.json").read_text(encoding="utf-8")))
    return _BASELINE


def original(rel):
    return baseline()["files"][rel]


def harness_files(workspace):
    if not (Path(workspace) / ".git").exists():
        return set()
    try:
        roots = subprocess.run(["git", "rev-list", "--max-parents=0", "HEAD"], cwd=workspace,
                               capture_output=True, text=True, timeout=30).stdout.split()
        if not roots:
            return set()
        listed = subprocess.run(["git", "ls-tree", "-r", "--name-only", roots[-1]], cwd=workspace,
                                capture_output=True, text=True, timeout=30).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return set()
    return set(listed) - set(baseline()["hashes"])


def compare(workspace):
    before, after = dict(baseline()["hashes"]), snapshot(workspace)
    for extra in harness_files(workspace):
        after.pop(extra, None)
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    return added, removed, changed


def run_python(code, workspace, timeout=60, extra_env=None, args=(), cwd=None):
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp, "probe.py")
        script.write_text(code)
        env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
        env.update({"PYTHONPATH": str(workspace), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"})
        env.update(extra_env or {})
        try:
            return subprocess.run(
                [sys.executable, str(script), *args],
                cwd=cwd or tmp, env=env, capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess([], 124, "", "timeout")


def probe_json(code, workspace, **kwargs):
    result = run_python(code, workspace, **kwargs)
    for line in reversed(result.stdout.splitlines()):
        if line.startswith("@@RESULT "):
            return json.loads(line[len("@@RESULT "):]), result
    return None, result


def test_functions(source):
    tree = ast.parse(source)
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            found[node.name + ".__class__"] = repr([ast.dump(d) for d in node.decorator_list])
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                    item.name.startswith("test") or item.name in ("setUp", "tearDown", "setUpClass", "tearDownClass")
                ):
                    found[node.name + "." + item.name] = ast.dump(item)
    return found


def changed_tests(original_source, current_source):
    before = test_functions(original_source)
    try:
        after = test_functions(current_source)
    except SyntaxError:
        return sorted(before)
    return sorted(name for name, dump in before.items() if after.get(name) != dump)


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


class Grade:
    def __init__(self):
        self.checks = []

    def add(self, name, passed, detail="", required=True):
        prefix = "" if required else "[advisory] "
        self.checks.append({"name": name, "passed": bool(passed), "detail": prefix + str(detail)[:600], "required": required})

    def summary_checks(self, workspace):
        text = read_text(Path(workspace, "SUMMARY.md"))
        self.add("instruction-summary-written", text is not None and len(text.strip()) >= 80,
                 "SUMMARY.md present" if text else "SUMMARY.md missing")
        return text or ""

    def emit(self):
        passed = bool(self.checks) and all(c["passed"] for c in self.checks if c["required"])
        score = round(sum(c["passed"] for c in self.checks) / len(self.checks), 3) if self.checks else 0.0
        print(json.dumps({
            "passed": passed,
            "score": score,
            "checks": [{"name": c["name"], "passed": c["passed"], "detail": c["detail"]} for c in self.checks],
        }))


def main(grade_fn):
    grade = Grade()
    try:
        if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
            raise SystemExit("usage: run.py <workspace>")
        grade_fn(Path(sys.argv[1]).resolve(), grade)
    except BaseException as exc:
        grade.add("grader-error", False, repr(exc))
    grade.emit()


# ---------------------------------------------------------------------------------------------------------
# Task-specific part: held-out datasets, an independent oracle written from docs/RECONCILIATION.md, and checks.
# ---------------------------------------------------------------------------------------------------------
import random
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from zoneinfo import ZoneInfo

UTC = timezone.utc
EXPONENT = {"JPY": 0, "KRW": 0, "CLP": 0, "VND": 0, "KWD": 3, "BHD": 3, "JOD": 3}
SAMPLE_MERCHANTS = ["m-aoba-books", "m-brightside-cafe", "m-cedar-foods", "m-dune-outfit", "m-evergreen-tea",
                    "m-fjord-travel", "m-gamma-lab", "m-harbour-fish", "m-iris-kuwait"]
FIELDS = ("currency", "charges_minor", "refunds_minor", "fee_minor", "net_minor")


def exp10(code):
    return EXPONENT.get(code, 2)


def rhe(value):
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def oracle(ds):
    """Payouts per the contract: {(merchant, day): (currency, charges, refunds, fee, net)} or the string 'ValueError'."""
    merchants = {m["merchant_id"]: m for m in ds["merchants"]}
    rates = {(r["day"], r["from"], r["to"]): Decimal(r["rate"]) for r in ds["rates"]}
    seen, buckets = set(), {}
    for e in ds["events"]:
        if e["status"] != "succeeded":
            continue
        key = (e["merchant_id"], e["currency"], e["event_id"])
        if key in seen:
            continue
        seen.add(key)
        m = merchants[e["merchant_id"]]
        t = datetime.strptime(e["occurred_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        day = t.astimezone(ZoneInfo(m["timezone"])).date().isoformat()
        buckets.setdefault((e["merchant_id"], day), []).append(e)
    out = {}
    with localcontext() as ctx:
        ctx.prec = 60
        for (mid, day), evs in sorted(buckets.items()):
            m = merchants[mid]
            settle = m["settlement_currency"]
            charges = refunds = count = 0
            for e in evs:
                amount = e["amount_minor"]
                if e["currency"] != settle:
                    rate = rates.get((day, e["currency"], settle))
                    if rate is None:
                        return "ValueError"
                    amount = rhe(Decimal(amount) / Decimal(10) ** exp10(e["currency"]) * rate * Decimal(10) ** exp10(settle))
                if e["type"] == "charge":
                    charges += amount
                    count += 1
                elif e["type"] == "refund":
                    refunds += amount
                else:
                    refunds -= amount
            base = charges - refunds
            fee = (rhe(Decimal(base) * m["fee_bps"] / Decimal(10000)) if base > 0 else 0) + m["fixed_fee_minor"] * count
            out[(mid, day)] = (settle, charges, refunds, fee, charges - refunds - fee)
    return out


class Builder:
    def __init__(self, seed):
        self.rnd = random.Random(seed)
        self.events, self.merchants, self.counters = [], [], {}

    def merchant(self, mid, tz, cur, bps=0, fixed=0):
        self.merchants.append({"merchant_id": mid, "name": mid, "timezone": tz, "settlement_currency": cur,
                               "fee_bps": bps, "fixed_fee_minor": fixed})

    def put(self, mid, kind, cur, amount, when, status="succeeded", retries=0, eid=None):
        if eid is None:
            self.counters[(mid, cur)] = n = self.counters.get((mid, cur), 0) + 1
            eid = f"{kind[:2]}-{n:04d}"
        row = {"event_id": eid, "merchant_id": mid, "type": kind, "status": status, "currency": cur, "amount_minor": amount,
               "occurred_at": when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "received_at": (when.astimezone(UTC) + timedelta(seconds=3)).strftime("%Y-%m-%dT%H:%M:%SZ")}
        self.events.append(row)
        for i in range(retries):
            copy = dict(row)
            copy["received_at"] = (when.astimezone(UTC) + timedelta(seconds=60 * (i + 1))).strftime("%Y-%m-%dT%H:%M:%SZ")
            self.events.append(copy)
        return row

    def local(self, tz, day, h=0, m=0, s=0):
        return datetime(day.year, day.month, day.day, h, m, s, tzinfo=ZoneInfo(tz))

    def amount(self, cur, lo=1, hi=200):
        major = self.rnd.randint(lo, hi)
        if cur == "JPY" or EXPONENT.get(cur) == 0:
            return major * self.rnd.choice([1, 7, 50, 100, 133])
        return major * 10 ** exp10(cur) + self.rnd.randint(0, 10 ** exp10(cur) - 1)

    def dataset(self, wobble=True, fixed_rates=None, extra_rates=()):
        needed = {}
        for m in self.merchants:
            for cur in {e["currency"] for e in self.events if e["merchant_id"] == m["merchant_id"]}:
                if cur != m["settlement_currency"]:
                    needed[(cur, m["settlement_currency"])] = True
        days = [datetime.strptime(e["occurred_at"], "%Y-%m-%dT%H:%M:%SZ").date() for e in self.events]
        lo, hi = min(days) - timedelta(days=2), max(days) + timedelta(days=2)
        rates, rnd = [], random.Random(7)
        for (src, dst) in sorted(needed):
            base = (fixed_rates or {}).get((src, dst)) or Decimal(rnd.choice(["0.9234", "162.35", "0.0061", "1.195", "0.3335", "3.67", "0.00895", "149.2"]))
            d = lo
            while d <= hi:
                rate = base if not wobble else (base * (1 + Decimal((d.toordinal() * 37) % 61 - 30) / 1000)).quantize(Decimal("0.000001"))
                rates.append({"day": d.isoformat(), "from": src, "to": dst, "rate": str(rate)})
                d += timedelta(days=1)
        rates.extend(extra_rates)
        order = self.rnd.sample(range(len(self.events)), len(self.events)) if False else range(len(self.events))
        return {"events": [self.events[i] for i in order], "merchants": self.merchants, "rates": rates}


def write_dataset(ds, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in ds["events"]))
    (directory / "merchants.json").write_text(json.dumps(ds["merchants"]))
    lines = ["day,from,to,rate"] + [f"{r['day']},{r['from']},{r['to']},{r['rate']}" for r in ds["rates"]]
    (directory / "rates.csv").write_text("\n".join(lines) + "\n")


def identity_dataset():
    b = Builder(101)
    b.merchant("h-one", "UTC", "EUR", 0, 10)
    b.merchant("h-two", "UTC", "EUR", 0, 10)
    b.merchant("h-three", "Europe/Paris", "USD", 120, 0)
    days = [date(2025, 6, 10) + timedelta(i) for i in range(3)]
    for mid, curs in (("h-one", ["EUR", "USD", "GBP", "CAD"]), ("h-two", ["EUR", "USD", "GBP"]), ("h-three", ["USD", "EUR"])):
        for day in days:
            for cur in curs:
                for k in range(7):
                    when = b.local("UTC" if mid != "h-three" else "Europe/Paris", day, b.rnd.randint(1, 22), b.rnd.randint(0, 59), b.rnd.randint(0, 59))
                    kind = "charge" if k < 5 else ("refund" if k == 5 else "refund_reversal")
                    amount = b.amount(cur)
                    if b.rnd.random() < 0.15:
                        b.put(mid, kind, cur, amount, when, status="failed")
                        b.counters[(mid, cur)] -= 1
                    b.put(mid, kind, cur, amount, when, retries=b.rnd.choice([0, 0, 1, 3]))
    return b.dataset()


ZONE_EDGES = [
    ("Europe/Berlin", [date(2025, 3, 30), date(2025, 10, 26), date(2024, 3, 31), date(2025, 12, 31)]),
    ("America/New_York", [date(2025, 3, 9), date(2025, 11, 2), date(2024, 11, 3)]),
    ("Australia/Sydney", [date(2025, 4, 6), date(2025, 10, 5), date(2025, 12, 31)]),
    ("Pacific/Auckland", [date(2025, 4, 6), date(2025, 9, 28)]),
    ("Europe/London", [date(2025, 3, 30), date(2025, 10, 26), date(2025, 7, 1)]),
    ("Asia/Kolkata", [date(2025, 6, 30)]),
    ("America/St_Johns", [date(2025, 3, 9), date(2025, 11, 2)]),
    ("Pacific/Chatham", [date(2025, 4, 6), date(2025, 9, 28)]),
    ("America/Phoenix", [date(2025, 7, 4)]),
    ("Asia/Tokyo", [date(2025, 1, 1)]),
]


def day_dataset():
    b = Builder(202)
    for i, (tz, edges) in enumerate(ZONE_EDGES):
        mid = f"z{i}-{tz.split('/')[1].lower()}"
        b.merchant(mid, tz, "USD", 0, 0)
        for edge in edges:
            for off in (-1, 0, 1):
                day = edge + timedelta(days=off)
                for (h, m, s) in ((0, 0, 0), (0, 0, 1), (0, 59, 59), (12, 0, 0), (23, 0, 0), (23, 59, 59)):
                    b.put(mid, "charge", "USD", b.rnd.randint(100, 99999), b.local(tz, day, h, m, s))
    b.merchant("zx-berlin-usd", "Europe/Berlin", "EUR", 0, 0)
    b.merchant("zx-sydney-eur", "Australia/Sydney", "EUR", 0, 0)
    for tz, mid, edge in (("Europe/Berlin", "zx-berlin-usd", date(2025, 3, 30)), ("Australia/Sydney", "zx-sydney-eur", date(2025, 4, 6))):
        for off in (-1, 0, 1):
            day = edge + timedelta(days=off)
            for (h, m, s) in ((0, 0, 5), (0, 40, 0), (23, 30, 0), (23, 59, 59)):
                b.put(mid, "charge", "USD", b.rnd.randint(100, 99999), b.local(tz, day, h, m, s))
    return b.dataset()


def fee_dataset():
    b = Builder(303)
    specs = [("f-tie250", "EUR", 250, 0), ("f-tie250-fixed", "USD", 250, 30), ("f-bps290", "EUR", 290, 25), ("f-zero", "EUR", 0, 15),
             ("f-yen", "JPY", 290, 0), ("f-yen-fixed", "JPY", 175, 10), ("f-dinar", "KWD", 125, 100), ("f-bps1", "USD", 1, 0),
             ("f-high", "EUR", 1499, 5)]
    for mid, cur, bps, fixed in specs:
        b.merchant(mid, "UTC", cur, bps, fixed)
        for d in range(4):
            day = date(2025, 5, 5) + timedelta(d)
            for k in range(b.rnd.randint(18, 30)):
                b.put(mid, "charge", cur, b.amount(cur, 1, 60), b.local("UTC", day, b.rnd.randint(0, 23), b.rnd.randint(0, 59)))
            for k in range(b.rnd.randint(0, 3)):
                b.put(mid, "refund", cur, b.amount(cur, 1, 25), b.local("UTC", day, b.rnd.randint(0, 23), b.rnd.randint(0, 59)))
    b.merchant("f-ties", "UTC", "EUR", 250, 0)
    for day_n, amounts in enumerate(([10, 10], [30, 30], [50, 30, 20], [70], [20, 40, 60, 80], [130])):
        for a in amounts:
            b.put("f-ties", "charge", "EUR", a, b.local("UTC", date(2025, 5, 5) + timedelta(day_n), 9, a % 50))
    return b.dataset()


def fx_dataset():
    b = Builder(404)
    currencies = ["EUR", "USD", "JPY", "KRW", "KWD", "BHD", "JOD", "CLP", "VND", "GBP"]
    fixed, rnd = {}, random.Random(9)
    for settle in ["EUR", "JPY", "KWD", "KRW", "USD", "BHD"]:
        mid = f"c-{settle.lower()}"
        b.merchant(mid, "Europe/Zurich", settle, 0, 0)
        for cur in currencies:
            if cur == settle:
                continue
            fixed[(cur, settle)] = Decimal(rnd.choice(["0.5", "2.5", "0.0061", "162.35", "0.3335", "3.0", "0.25", "149.2", "0.00895", "0.0025"]))
            for k in range(5):
                day = date(2025, 8, 11) + timedelta(rnd.randint(0, 2))
                amount = rnd.choice([100, 300, 500, 700, 12345, 1, 99999]) if k < 3 else b.amount(cur, 1, 900)
                b.put(mid, rnd.choice(["charge", "charge", "refund"]), cur, amount, b.local("Europe/Zurich", day, rnd.randint(1, 22), rnd.randint(0, 59)))
        for k in range(4):
            b.put(mid, "charge", settle, b.amount(settle), b.local("Europe/Zurich", date(2025, 8, 11) + timedelta(k % 3), 10, k))
    return b.dataset(wobble=False, fixed_rates=fixed)


def missing_rate_dataset():
    b = Builder(505)
    b.merchant("r-one", "UTC", "EUR", 0, 0)
    b.put("r-one", "charge", "JPY", 5000, b.local("UTC", date(2025, 2, 3), 10))
    ds = b.dataset()
    ds["rates"] = [r for r in ds["rates"] if r["day"] != "2025-02-03"]
    return ds


def refund_dataset():
    b = Builder(606)
    plan = [("n-eur", "UTC", "EUR", 290, 30), ("n-yen", "Asia/Tokyo", "JPY", 250, 0), ("n-usd", "America/New_York", "USD", 150, 20),
            ("n-kwd", "Asia/Kuwait", "KWD", 125, 50)]
    for mid, tz, cur, bps, fixed in plan:
        b.merchant(mid, tz, cur, bps, fixed)
        d0 = date(2025, 9, 1)
        charges = [b.put(mid, "charge", cur, b.amount(cur, 5, 80), b.local(tz, d0, 8 + k, 13)) for k in range(6)]
        for k, c in enumerate(charges[:4]):  # day 2: refunds only, no charge: negative payout
            b.put(mid, "refund", cur, c["amount_minor"] - (k % 2), b.local(tz, d0 + timedelta(1), 9 + k, 5))
        b.put(mid, "refund", cur, 5, b.local(tz, d0 + timedelta(1), 20, 5), status="pending")
        for k in range(5):  # day 3: charges, a refund and a reversal larger than the refund
            b.put(mid, "charge", cur, b.amount(cur, 5, 80), b.local(tz, d0 + timedelta(2), 7 + k, 21))
        b.put(mid, "refund", cur, 7, b.local(tz, d0 + timedelta(2), 15, 0))
        b.put(mid, "refund_reversal", cur, 4 * 10 ** exp10(cur) + 1, b.local(tz, d0 + timedelta(2), 16, 0))
        b.put(mid, "refund_reversal", cur, 3, b.local(tz, d0 + timedelta(3), 11, 0))  # day 4: reversal only
        b.put(mid, "refund", cur, 1, b.local(tz, d0 + timedelta(4), 11, 0), retries=2)  # day 5: refund counted once
        b.put(mid, "charge", cur, 3, b.local(tz, d0 + timedelta(4), 12, 0))
        b.put(mid, "charge", cur, b.amount(cur), b.local(tz, d0 + timedelta(4), 13, 0), status="failed")
    b.merchant("n-mix", "Europe/Berlin", "EUR", 275, 40)
    for k in range(10):
        cur = ["EUR", "JPY", "USD"][k % 3]
        b.put("n-mix", "charge", cur, b.amount(cur, 3, 90), b.local("Europe/Berlin", date(2025, 9, 1), 9 + k, 10))
    b.put("n-mix", "refund", "USD", 777, b.local("Europe/Berlin", date(2025, 9, 1), 22, 0))
    b.put("n-mix", "refund", "JPY", 4500, b.local("Europe/Berlin", date(2025, 9, 1), 22, 5))
    b.put("n-mix", "refund_reversal", "JPY", 1200, b.local("Europe/Berlin", date(2025, 9, 1), 22, 6))
    return b.dataset()


def mixed_dataset(seed, start, span, zones):
    b = Builder(seed)
    currencies = ["EUR", "USD", "JPY", "KWD", "GBP", "AUD", "KRW", "CHF"]
    rnd = b.rnd
    for i, tz in enumerate(zones):
        settle = rnd.choice(currencies)
        b.merchant(f"x{seed}-{i:02d}", tz, settle, rnd.choice([0, 100, 190, 250, 290, 325, 1000]), rnd.choice([0, 0, 10, 35]))
    merchants = list(b.merchants)
    for m in merchants:
        mine = rnd.sample(currencies, 3) + [m["settlement_currency"]]
        for k in range(110):
            day = start + timedelta(rnd.randint(0, span))
            if rnd.random() < 0.4:
                secs = rnd.choice([0, 1, 59, 3599, 3600, 86399, 86398, 82800]) + rnd.randint(-20, 20)
                secs = min(max(secs, 0), 86399)
            else:
                secs = rnd.randint(0, 86399)
            when = b.local(m["timezone"], day, secs // 3600, (secs % 3600) // 60, secs % 60)
            cur = rnd.choice(mine)
            kind = rnd.choices(["charge", "refund", "refund_reversal"], weights=[8, 2, 1])[0]
            status = rnd.choices(["succeeded", "failed", "pending"], weights=[20, 1, 1])[0]
            b.put(m["merchant_id"], kind, cur, b.amount(cur, 1, 300), when, status=status, retries=rnd.choice([0, 0, 0, 1, 2]))
    return b.dataset()


MIXED_ZONES = ["Europe/Berlin", "America/New_York", "Australia/Sydney", "Asia/Kolkata", "Pacific/Auckland", "Europe/London",
               "UTC", "America/St_Johns", "Asia/Tokyo", "America/Los_Angeles"]


def groups():
    return {
        "event-identity": [("identity", identity_dataset())],
        "settlement-day": [("zones", day_dataset())],
        "fee-rounding": [("fees", fee_dataset())],
        "currency-scaling": [("conversion", fx_dataset()), ("missing-rate", missing_rate_dataset())],
        "refund-netting": [("refunds", refund_dataset())],
        "mixed-held-out": [("spring", mixed_dataset(11, date(2025, 3, 26), 14, MIXED_ZONES)),
                           ("autumn", mixed_dataset(12, date(2025, 10, 22), 14, MIXED_ZONES[::-1])),
                           ("april", mixed_dataset(13, date(2025, 4, 1), 9, MIXED_ZONES[3:] + MIXED_ZONES[:3]))],
    }


PIPELINE_PROBE = r'''
import json, sys
from settle import pipeline
out = {}
for path in json.load(open(sys.argv[1])):
    try:
        out[path] = [vars(p) if hasattr(p, "__dict__") else {k: getattr(p, k) for k in p.__slots__} for p in pipeline.run(path)]
    except Exception as exc:
        out[path] = {"error": type(exc).__name__}
print("@@RESULT " + json.dumps(out))
'''


def compare_payouts(expected, got):
    """Problems between the oracle's payouts and the pipeline's, as short strings."""
    if expected == "ValueError":
        return [] if isinstance(got, dict) and got.get("error") == "ValueError" else [f"missing rate must raise ValueError, got {str(got)[:60]}"]
    if isinstance(got, dict):
        return [f"pipeline raised {got['error']}"]
    rows = {(p["merchant_id"], p["day"]): p for p in got}
    problems = []
    for key in sorted(set(expected) | set(rows)):
        want, have = expected.get(key), rows.get(key)
        if want is None:
            problems.append(f"{key[0]} {key[1]}: unexpected payout")
        elif have is None:
            problems.append(f"{key[0]} {key[1]}: payout missing")
        else:
            now = (have["currency"], have["charges_minor"], have["refunds_minor"], have["fee_minor"], have["net_minor"])
            if now != want:
                problems.append(f"{key[0]} {key[1]}: want {dict(zip(FIELDS, want))} got {dict(zip(FIELDS, now))}")
    return problems


def run_groups(ws):
    cases = groups()
    results = {}
    with tempfile.TemporaryDirectory() as tmp:
        index = {}
        for name, datasets in cases.items():
            for label, ds in datasets:
                path = str(Path(tmp, f"{name}-{label}"))
                write_dataset(ds, path)
                index[path] = (name, label, oracle(ds))
        listing = Path(tmp, "listing.json")
        listing.write_text(json.dumps(sorted(index)))
        res, raw = probe_json(PIPELINE_PROBE, ws, args=(str(listing),), timeout=240)
    if res is None:
        return None, raw.stderr[-500:]
    for path, (name, label, expected) in index.items():
        problems = compare_payouts(expected, res[path])
        total = 1 if expected == "ValueError" else len(expected)
        results.setdefault(name, []).append((label, problems, total))
    return results, ""


def sample_reconciles(ws):
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        run = subprocess.run([sys.executable, "tools/reconcile.py"], cwd=ws, capture_output=True, text=True, timeout=120, env=env)
    except subprocess.TimeoutExpired:
        return False, "timeout"
    lines = [l for l in run.stdout.splitlines() if l.strip()]
    return run.returncode == 0, (lines[-1] if lines else run.stderr[-200:])


def code_literals(path):
    found = set()
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return found
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            found.add(node.value)
    return found


def grade(ws, g):
    added, removed, changed = compare(ws)
    touched = added + removed + changed
    outside = [p for p in touched if not p.startswith(("settle/", "tests/")) and p != "SUMMARY.md"]
    g.add("only-allowed-files-changed", not outside, f"outside allowed paths: {outside}" if outside else "ok")
    modified = []
    for rel in ("tests/test_units.py", "tests/test_reconcile.py"):
        current = read_text(ws / rel)
        modified += [f"{rel}: file removed"] if current is None else [f"{rel}: {n}" for n in changed_tests(original(rel), current)]
    g.add("existing-tests-unchanged", not modified, f"modified: {modified}" if modified else "ok")
    frozen = [p for p in touched if p.startswith(("data/", "docs/", "tools/"))]
    g.add("reference-data-untouched", not frozen, f"changed data, docs or tools: {frozen}" if frozen else "ok")

    literals = set()
    for py in (ws / "settle").rglob("*.py"):
        literals |= code_literals(py)
    hits = sorted(l for l in literals if any(m in l for m in SAMPLE_MERCHANTS) or "bank_statement" in l)
    g.add("no-special-casing", not hits, f"sample merchants or the statement named in settle/: {hits[:5]}" if hits else "ok")

    ok, detail = sample_reconciles(ws)
    g.add("sample-reconciles", ok, detail)
    results, error = run_groups(ws)
    tally = [0, 0]

    def verdict(name):
        if results is None:
            return False, "probe crashed: " + error
        problems = [f"[{label}] {p}" for label, probs, _ in results[name] for p in probs]
        count = sum(t for _, _, t in results[name])
        tally[0] += len(problems)
        tally[1] += count
        return not problems, (f"{len(problems)} of {count} wrong: " + "; ".join(problems[:3]) if problems else f"all {count} payouts match")

    g.add("event-identity", *verdict("event-identity"))
    g.add("settlement-day", *verdict("settlement-day"))
    g.add("currency-scaling", *verdict("currency-scaling"))
    g.add("fee-rounding", *verdict("fee-rounding"))
    g.add("refund-netting", *verdict("refund-netting"))
    g.add("mixed-held-out", *verdict("mixed-held-out"))
    wrong, total = tally
    g.add("held-out-mostly-right", results is not None and wrong <= total // 20, f"{wrong} of {total} wrong", required=False)
    text = g.summary_checks(ws)
    low = text.lower()
    named = [k for k in ("dedupe", "days", "fees", "fx") if k in low]
    g.add("summary-names-the-causes", len(named) == 4, f"summary mentions {named}", required=False)


if __name__ == "__main__":
    main(grade)
