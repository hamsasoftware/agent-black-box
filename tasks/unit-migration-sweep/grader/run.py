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


NORMALIZE = [("2", "2.000"), ("1.5", "1.500"), ("0.250", "0.250"), ("0", "0.000"), ("1.2345", "1.234"),
             ("1.0005", "1.000"), ("1.0015", "1.002"), ("2.0025", "2.002"), ("0.0005", "0.000"), ("0.0015", "0.002"),
             ("0.00051", "0.001"), ("0.0004999", "0.000"), ("1000000", "1000000.000"), ("2147483.647", "2147483.647"),
             ("12345678901234567890.1235", "12345678901234567890.124")]
INVALID_WEIGHTS = ["", "-1", "+1", "1e3", "1E3", "nan", "NaN", "inf", " 1", "1 ", "1,5", "1.", ".5", ".", "abc",
                   "1.2.3", "0x10", "１", "1_000", "-0", 1500, 1.5, True, None]
KG_TO_G = [("1.25", 1250), ("0.001", 1), ("1000", 1000000), ("1.0005", 1000), ("2147483.647", 2147483647), ("0", 0)]
G_TO_KG = [(1250, "1.250"), (0, "0.000"), (1, "0.001"), (2147483647, "2147483.647"), (999, "0.999")]
INVALID_GRAMS = [-1, 1.0, "5", True, None]
RATES = [("0.000", "eu", 400), ("0.001", "eu", 400), ("0.500", "eu", 400), ("0.501", "eu", 490), ("1.000", "eu", 490),
         ("1.001", "eu", 580), ("2.000", "us", 1350), ("9.999", "world", 6440), ("10.000", "world", 6440),
         ("10.001", "world", 7200), ("20.000", "eu", 4410), ("0.5", "eu", 400), ("0.5004", "eu", 400),
         ("0.5005", "eu", 400), ("0.5015", "eu", 490)]
VALIDATE = [
    ({"sku": "A", "weight_kg": "1.500", "qty": 1}, []),
    ({"sku": "A", "weight_kg": "0.001", "qty": 1}, []),
    ({"sku": "A", "weight_kg": "1000.000", "qty": 1000}, []),
    ({"sku": "A", "weight_kg": "1000.0004", "qty": 1}, []),
    ({"sku": "A", "weight_kg": "0.0015", "qty": 1}, []),
    ({"sku": "A", "weight_kg": "2", "qty": 1}, []),
    ({"sku": "A", "weight_kg": "1000.001", "qty": 1}, ["weight_kg"]),
    ({"sku": "A", "weight_kg": "0.0004", "qty": 1}, ["weight_kg"]),
    ({"sku": "A", "weight_kg": "0.0005", "qty": 1}, ["weight_kg"]),
    ({"sku": "A", "weight_kg": "0", "qty": 1}, ["weight_kg"]),
    ({"sku": "A", "weight_kg": "-1", "qty": 1}, ["weight_kg"]),
    ({"sku": "A", "weight_kg": "abc", "qty": 1}, ["weight_kg"]),
    ({"sku": "A", "weight_kg": 1500, "qty": 1}, ["weight_kg"]),
    ({"sku": "A", "weight_kg": 1.5, "qty": 1}, ["weight_kg"]),
    ({"sku": "A", "weight_kg": None, "qty": 1}, ["weight_kg"]),
    ({"sku": "A", "weight_g": 1500, "qty": 1}, ["weight_kg"]),
    ({"sku": "", "weight_kg": "1", "qty": 1}, ["sku"]),
    ({"sku": "A", "weight_kg": "1", "qty": 0}, ["qty"]),
    ({"sku": "A", "weight_kg": "1", "qty": 1001}, ["qty"]),
    ({"sku": "", "weight_kg": "x", "qty": 0}, ["sku", "weight_kg", "qty"]),
]

PROBE = r'''
import json, sys, traceback
from decimal import Decimal

bad = {}


def fail(area, text):
    bad.setdefault(area, []).append(text)


def area(name):
    def wrap(fn):
        try:
            fn(lambda text: fail(name, text))
        except BaseException:
            fail(name, "area crashed: " + traceback.format_exc().strip().splitlines()[-1])
        return fn
    return wrap


def raises(call, *types):
    try:
        call()
    except types:
        return True
    except BaseException:
        return False
    return False


def order_of(*rows):
    from shipcalc.models import Item, Order
    return Order(Item(*row) for row in rows)


data = json.load(open(sys.argv[1]))


@area("weight-core")
def _(f):
    from shipcalc.units import WeightError, normalize_kg, kg_to_g, g_to_kg
    from shipcalc.models import Item, Order
    from shipcalc.calc import order_weight_kg
    if not issubclass(WeightError, ValueError):
        f("WeightError is not a ValueError")
    for given, want in data["normalize"]:
        got = normalize_kg(given)
        if got != want or type(got) is not str:
            f(f"normalize_kg({given!r}) = {got!r}, want {want!r}")
    for given in data["invalid_weights"] + [b"1", ["1"], Decimal("1.5")]:
        try:
            normalize_kg(given)
            f(f"normalize_kg({given!r}) accepted")
        except WeightError as exc:
            if str(exc) != f"invalid weight: {given!r}":
                f(f"message for {given!r} is {str(exc)!r}")
        except BaseException as exc:
            f(f"normalize_kg({given!r}) raised {exc!r}")
        if not raises(lambda: Item("A", given), WeightError):
            f(f"Item(weight={given!r}) did not raise WeightError")
        if not raises(lambda: kg_to_g(given), WeightError):
            f(f"kg_to_g({given!r}) did not raise WeightError")
    for given, want in data["kg_to_g"]:
        got = kg_to_g(given)
        if got != want or type(got) is not int:
            f(f"kg_to_g({given!r}) = {got!r}, want {want!r}")
    for given, want in data["g_to_kg"]:
        got = g_to_kg(given)
        if got != want:
            f(f"g_to_kg({given!r}) = {got!r}, want {want!r}")
    for given in data["invalid_grams"]:
        if not raises(lambda: g_to_kg(given), WeightError):
            f(f"g_to_kg({given!r}) did not raise WeightError")
    item = Item("A", "1.5", 2)
    if (item.weight_kg, item.line_weight_kg(), item.to_dict()) != ("1.500", "3.000", {"sku": "A", "weight_kg": "1.500", "qty": 2}):
        f(f"Item basics: {item.weight_kg!r} {item.line_weight_kg()!r} {item.to_dict()!r}")
    if Item("A", "0.333", 3).line_weight_kg() != "0.999":
        f("line_weight_kg of 0.333 x 3")
    if Item("A", "1.0005").weight_kg != "1.000" or Item("A", "1.0015").weight_kg != "1.002":
        f("Item does not round half to even")
    if Item.from_dict({"sku": "A", "weight_kg": "2.5"}).weight_kg != "2.500":
        f("Item.from_dict")
    total = order_weight_kg(order_of(("a", "0.1", 3), ("b", "0.2", 1)))
    if total != "0.500":
        f(f"order_weight_kg = {total!r}, want '0.500'")
    if order_weight_kg(Order()) != "0.000":
        f("empty order weight")
    if order_weight_kg(order_of(("a", "0.333", 3), ("b", "1.001", 7))) != "8.006":
        f("order_weight_kg of 0.333x3 + 1.001x7")


@area("rates-packing")
def _(f):
    from shipcalc.rates import shipping_cents
    from shipcalc.packing import split_parcels
    from shipcalc.calc import quote
    from shipcalc.units import WeightError
    for weight, zone, want in data["rates"]:
        got = shipping_cents(weight, zone)
        if got != want:
            f(f"shipping_cents({weight!r}, {zone!r}) = {got!r}, want {want}")
    if not raises(lambda: shipping_cents(500, "eu"), WeightError):
        f("shipping_cents(500) did not raise WeightError")
    if not raises(lambda: shipping_cents("1.000", "mars"), ValueError):
        f("unknown zone")
    cases = [
        ([("B", "12.000"), ("A", "8.000"), ("C", "8.000")], [("20.000", ["B", "A"]), ("8.000", ["C"])]),
        ([("X", "25.5"), ("Y", "0.5")], [("25.500", ["X"]), ("0.500", ["Y"])]),
        ([("S", "9.000"), ("T", "10.000"), ("U", "9.500")], [("19.500", ["T", "U"]), ("9.000", ["S"])]),
        ([("Q", "7.000", 3)], [("14.000", ["Q", "Q"]), ("7.000", ["Q"])]),
        ([("M", "20.000"), ("N", "0.001")], [("20.000", ["M"]), ("0.001", ["N"])]),
    ]
    for rows, want in cases:
        got = [(p.weight_kg, p.skus) for p in split_parcels(order_of(*rows))]
        if got != want:
            f(f"split_parcels({rows}) = {got}, want {want}")
    got = quote(order_of(("B", "12.000"), ("A", "8.000"), ("C", "8.000")), "eu")
    if got != {"parcels": 2, "weight_kg": "28.000", "cents": 6160}:
        f(f"quote = {got}")


@area("carrier-limit")
def _(f):
    from shipcalc.units import WeightError
    from shipcalc.limits import check_total_kg
    from shipcalc.calc import order_weight_kg
    if check_total_kg("2147483.647") != "2147483.647":
        f("exactly the limit must be accepted")
    if check_total_kg("1.5") != "1.500":
        f("check_total_kg does not return the canonical weight")
    for given in ("2147483.648", "3000000", "99999999999"):
        try:
            check_total_kg(given)
            f(f"check_total_kg({given!r}) accepted")
        except WeightError:
            pass
        except BaseException as exc:
            f(f"check_total_kg({given!r}) raised {exc!r}, want WeightError")
    if not raises(lambda: check_total_kg(5), WeightError):
        f("check_total_kg(5) did not raise WeightError")
    if order_weight_kg(order_of(("H", "1000.000", 2147), ("I", "483.647"))) != "2147483.647":
        f("order at the limit")
    for rows in ([("H", "1000.000", 2147), ("I", "483.647"), ("J", "0.001")], [("H", "1000.000", 1000)] * 3):
        try:
            order_weight_kg(order_of(*rows))
            f("order over the limit accepted")
        except WeightError:
            pass
        except BaseException as exc:
            f(f"order over the limit raised {exc!r}")


@area("validator")
def _(f):
    from shipcalc.validate import validate_item
    for raw, fields in data["validate"]:
        problems = validate_item(dict(raw))
        got = [p.split(":")[0] for p in problems]
        if got != fields or not all(": " in p for p in problems):
            f(f"validate_item({raw}) = {problems}, want problems on {fields}")
    if validate_item({"sku": "A", "weight_g": 1500, "qty": 1}) != ["weight_kg: missing"]:
        f(f"old weight_g key: {validate_item({'sku': 'A', 'weight_g': 1500, 'qty': 1})}")


@area("cache-key")
def _(f):
    from shipcalc import cache
    from shipcalc.calc import quote
    from shipcalc.models import Order
    got = cache.quote_key(order_of(("a", "0.350", 2), ("b", "1.2")), "eu")
    if got != "quote:v2:eu:1.900:2":
        f(f"quote_key = {got!r}")
    if cache.quote_key(order_of(("a", "1.5")), "us") != cache.quote_key(order_of(("a", "1.500")), "us"):
        f("1.5 and 1.500 give different keys")
    if cache.quote_key(Order(), "us") != "quote:v2:us:0.000:0":
        f(f"empty order key {cache.quote_key(Order(), 'us')!r}")
    cache.clear()
    order = order_of(("a", "0.350", 2), ("b", "1.2"))
    first = cache.cached_quote(order, "eu")
    if first != quote(order, "eu") or cache.cached_quote(order, "eu") is not first:
        f("cached_quote")


@area("storage")
def _(f):
    import os, tempfile
    from shipcalc import storage
    from shipcalc.units import WeightError
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "o.json")
        storage.save(order_of(("MUG", "0.35", 2), ("BOOK", "1.2")), path)
        raw = json.load(open(path))
        want = {"schema": 2, "items": [{"sku": "MUG", "weight_kg": "0.350", "qty": 2}, {"sku": "BOOK", "weight_kg": "1.200", "qty": 1}]}
        if raw != want:
            f(f"saved file is {raw}")
        loaded = storage.load(path)
        if [(i.sku, i.weight_kg, i.qty) for i in loaded.items] != [("MUG", "0.350", 2), ("BOOK", "1.200", 1)]:
            f("round trip")

        def write(payload):
            with open(path, "w") as handle:
                json.dump(payload, handle)
            return path

        old = write({"schema": 1, "items": [{"sku": "A", "weight_g": 350, "qty": 2}, {"sku": "B", "weight_g": 1}, {"sku": "C", "weight_g": 1200000}]})
        got = [(i.sku, i.weight_kg, i.qty) for i in storage.load(old).items]
        if got != [("A", "0.350", 2), ("B", "0.001", 1), ("C", "1200.000", 1)]:
            f(f"schema 1 file loaded as {got}")
        new = write({"schema": 2, "items": [{"sku": "A", "weight_kg": "1.5"}]})
        if [i.weight_kg for i in storage.load(new).items] != ["1.500"]:
            f("schema 2 weight not normalised")
        for payload in ({"schema": 1, "items": [{"sku": "A", "weight_g": "350"}]}, {"schema": 1, "items": [{"sku": "A", "weight_g": 1.5}]},
                        {"schema": 1, "items": [{"sku": "A", "weight_g": True}]}, {"schema": 2, "items": [{"sku": "A", "weight_kg": "x"}]},
                        {"schema": 2, "items": [{"sku": "A", "weight_kg": 350}]}):
            if not raises(lambda: storage.load(write(payload)), WeightError):
                f(f"invalid weight in {payload} did not raise WeightError")
        if not raises(lambda: storage.load(write({"schema": 3, "items": []})), ValueError):
            f("schema 3 must raise ValueError")


@area("export-stays-grams")
def _(f):
    from shipcalc.export import to_csv, carrier_payload
    from shipcalc.models import Order
    order = order_of(("MUG", "0.350", 2), ("BOOK", "1.2"), ("TINY", "0.001"), ("R", "1.0005"))
    if to_csv(order) != "sku,weight_g,qty\nMUG,350,2\nBOOK,1200,1\nTINY,1,1\nR,1000,1\n":
        f(f"to_csv = {to_csv(order)!r}")
    if to_csv(Order()) != "sku,weight_g,qty\n":
        f("empty csv")
    payload = carrier_payload(order)
    if json.dumps(payload, sort_keys=True) != '{"parcels": 1, "weight_g": 2901}':
        f(f"carrier_payload = {json.dumps(payload, sort_keys=True)}")


@area("text-output")
def _(f):
    from shipcalc.format import format_weight, format_table
    from shipcalc.units import WeightError
    for given, want in (("0.25", "0.250 kg"), ("12", "12.000 kg"), ("0.000", "0.000 kg"), ("1000", "1000.000 kg"), ("1.0005", "1.000 kg"), ("0.999", "0.999 kg")):
        got = format_weight(given)
        if got != want:
            f(f"format_weight({given!r}) = {got!r}, want {want!r}")
    if not raises(lambda: format_weight(250), WeightError):
        f("format_weight(250) did not raise WeightError")
    want = f"{'MUG-01':<12}{'0.350 kg':>12}  x2\n{'BOOK-07':<12}{'1.200 kg':>12}  x1"
    got = format_table(order_of(("MUG-01", "0.350", 2), ("BOOK-07", "1.2")))
    if got != want:
        f(f"format_table = {got!r}")


@area("reports")
def _(f):
    from shipcalc.reports import average_weight_kg, heaviest, weight_bands
    from shipcalc.models import Order
    cases = [
        ([("a", "0.001"), ("b", "0.000")], "0.000"), ([("a", "0.003"), ("b", "0.000")], "0.002"),
        ([("a", "0.005"), ("b", "0.000")], "0.002"), ([("a", "1.000"), ("b", "2.000", 2)], "1.667"),
        ([("a", "0.100", 3)], "0.100"), ([("a", "10.000"), ("b", "0.001")], "5.000"),
        ([("a", "10.002"), ("b", "0.001")], "5.002"), ([], "0.000"),
    ]
    for rows, want in cases:
        got = average_weight_kg(order_of(*rows))
        if got != want:
            f(f"average_weight_kg({rows}) = {got!r}, want {want!r}")
    order = order_of(("S", "9.000"), ("T", "10.000"), ("U", "9.500"), ("V", "9.500"))
    if [i.sku for i in heaviest(order)] != ["T", "U", "V"] or [i.sku for i in heaviest(order, 1)] != ["T"]:
        f(f"heaviest = {[i.sku for i in heaviest(order)]}")
    bands = weight_bands(order_of(("a", "0.500", 2), ("b", "0.501"), ("c", "2.000", 3), ("d", "2.001", 4), ("e", "10.000")))
    if bands != {"light": 2, "medium": 4, "heavy": 5}:
        f(f"weight_bands = {bands}")


print("@@RESULT " + json.dumps(bad))
'''

V1_ORDER = {"schema": 1, "items": [{"sku": "MUG-01", "weight_g": 350, "qty": 2}, {"sku": "BOOK-07", "weight_g": 1200}]}


def run_cli(ws, cwd, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env.update({"PYTHONPATH": str(ws), "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        return subprocess.run([sys.executable, "-m", "shipcalc", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", "timeout")


def cli_problems(ws):
    bad = []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp, "order.json")

        def write(payload):
            path.write_text(json.dumps(payload))

        write(V1_ORDER)
        shown = run_cli(ws, tmp, "show", str(path))
        want = f"{'MUG-01':<12}{'0.350 kg':>12}  x2\n{'BOOK-07':<12}{'1.200 kg':>12}  x1\ntotal weight: 1.900 kg\n"
        if (shown.returncode, shown.stdout) != (0, want):
            bad.append(f"show: rc {shown.returncode}, stdout {shown.stdout!r}, stderr {shown.stderr[-200:]!r}")
        quoted = run_cli(ws, tmp, "quote", str(path), "--zone", "eu")
        want = "items: 2\ntotal weight: 1.900 kg\nparcels: 1\nshipping: 6.70 EUR\n"
        if (quoted.returncode, quoted.stdout) != (0, want):
            bad.append(f"quote: rc {quoted.returncode}, stdout {quoted.stdout!r}, stderr {quoted.stderr[-200:]!r}")
        added = run_cli(ws, tmp, "add", str(path), "LAMP-3", "2.4", "1")
        raw = json.loads(path.read_text()) if added.returncode == 0 else None
        if raw is None or raw.get("schema") != 2 or raw["items"][-1] != {"sku": "LAMP-3", "weight_kg": "2.400", "qty": 1} or raw["items"][0].get("weight_kg") != "0.350":
            bad.append(f"add: rc {added.returncode}, file {raw}, stderr {added.stderr[-200:]!r}")
        else:
            again = run_cli(ws, tmp, "show", str(path))
            if "total weight: 4.300 kg" not in again.stdout:
                bad.append(f"show after add: {again.stdout!r} {again.stderr[-200:]!r}")
        write(V1_ORDER)
        before = path.read_text()
        for weight in ("abc", "-1", "1e3", "1,5"):
            failed = run_cli(ws, tmp, "add", str(path), "X", weight, "1")
            if (failed.returncode, failed.stderr, path.read_text()) != (2, f"error: invalid weight: {weight!r}\n", before):
                bad.append(f"add {weight!r}: rc {failed.returncode}, stderr {failed.stderr[-200:]!r}, file changed {path.read_text() != before}")
        run_cli(ws, tmp, "add", str(path), "T", "1.2345", "1")
        stored = json.loads(path.read_text())["items"][-1].get("weight_kg") if path.read_text() != before else None
        if stored != "1.234":
            bad.append(f"add 1.2345 stored {stored!r}")
        zone = run_cli(ws, tmp, "quote", str(path), "--zone", "mars")
        if (zone.returncode, zone.stderr) != (2, "error: unknown zone: 'mars'\n"):
            bad.append(f"quote unknown zone: rc {zone.returncode}, stderr {zone.stderr[-200:]!r}")
        write({"schema": 2, "items": [{"sku": f"H{i}", "weight_kg": "1000.000", "qty": 1000000} for i in range(3)]})
        over = run_cli(ws, tmp, "show", str(path))
        if over.returncode != 2 or not over.stderr.startswith("error: ") or "Traceback" in over.stderr:
            bad.append(f"show over the carrier limit: rc {over.returncode}, stderr {over.stderr[-200:]!r}")
    return bad


E2E = r'''
import json, os, sys, tempfile
from shipcalc import cache, storage
from shipcalc.calc import order_weight_kg, quote
from shipcalc.export import carrier_payload, to_csv
from shipcalc.units import g_to_kg, kg_to_g

problems = []
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "o.json")
    with open(path, "w") as handle:
        json.dump({"schema": 1, "items": [{"sku": "A", "weight_g": 333, "qty": 3}, {"sku": "B", "weight_g": 1250}, {"sku": "C", "weight_g": 12345, "qty": 2}]}, handle)
    order = storage.load(path)
    storage.save(order, path)
    order = storage.load(path)
    grams = 333 * 3 + 1250 + 12345 * 2
    weight = order_weight_kg(order)
    if weight != g_to_kg(grams) or kg_to_g(weight) != grams:
        problems.append(f"total {weight!r} does not match {grams} g")
    result = quote(order, "us")
    if result["weight_kg"] != weight:
        problems.append("quote weight differs from order weight")
    if weight not in cache.quote_key(order, "us"):
        problems.append("cache key does not carry the total weight")
    rows = [line.split(",") for line in to_csv(order).splitlines()[1:]]
    if sum(int(w) * int(q) for _, w, q in rows) != grams or carrier_payload(order)["weight_g"] != grams:
        problems.append("csv or carrier payload disagree with the total in grams")
print("@@RESULT " + json.dumps(problems))
'''


def changelog_problems(text):
    if text is None:
        return ["CHANGELOG.md missing"]
    match = re.search(r"^## \[Unreleased\]\s*$(.*?)(?=^## \[|\Z)", text, flags=re.MULTILINE | re.DOTALL)
    if not match:
        return ["no ## [Unreleased] section"]
    changed = re.search(r"^### Changed\s*$(.*?)(?=^##|\Z)", match.group(1), flags=re.MULTILINE | re.DOTALL)
    if not changed:
        return ["no ### Changed section under Unreleased"]
    bullets = [l for l in changed.group(1).splitlines() if l.lstrip().startswith(("- ", "* "))]
    if not any("weight_kg" in b and "kilogram" in b.lower() for b in bullets):
        return ["no bullet under Changed mentions weight_kg and kilograms"]
    if "### Added" not in match.group(1) or "weight_bands" not in match.group(1) or "[1.4.2]" not in text or "## [1.4.1]" not in text:
        return ["existing changelog content was removed"]
    return []


GRAM_NAME = re.compile(r"(^|_)(g|grams?)($|_)|weight_g", re.IGNORECASE)


def gram_names(root):
    found = []
    for py in sorted(Path(root, "shipcalc").rglob("*.py")):
        if py.name in ("export.py", "storage.py", "units.py"):
            continue
        try:
            tree = ast.parse(py.read_text())
        except SyntaxError:
            continue
        names = set()
        for node in ast.walk(tree):
            for name in (getattr(node, "id", None), getattr(node, "attr", None), getattr(node, "arg", None), getattr(node, "name", None)):
                if isinstance(name, str) and name not in ("g_to_kg", "kg_to_g") and GRAM_NAME.search(name):
                    names.add(name)
        if names:
            found.append(f"{py.name}: {sorted(names)}")
    return found


TEST_FILES = ("tests/test_models.py", "tests/test_calc.py", "tests/test_rates.py")


def grade(ws, g):
    added, removed, changed = compare(ws)
    touched = added + removed + changed
    outside = [p for p in touched if not p.startswith(("shipcalc/", "tests/")) and p not in ("CHANGELOG.md", "SUMMARY.md")]
    g.add("only-allowed-files-changed", not outside, f"outside allowed paths: {outside}" if outside else "ok")
    modified = []
    for rel in TEST_FILES:
        current = read_text(ws / rel)
        modified += [f"{rel}: file removed"] if current is None else [f"{rel}: {n}" for n in changed_tests(original(rel), current)]
    g.add("existing-tests-unchanged", not modified, f"modified: {modified}" if modified else "ok")

    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp, "cases.json")
        data.write_text(json.dumps({
            "normalize": NORMALIZE, "invalid_weights": INVALID_WEIGHTS,
            "kg_to_g": KG_TO_G, "g_to_kg": G_TO_KG, "invalid_grams": INVALID_GRAMS, "rates": RATES, "validate": VALIDATE,
        }))
        res, raw = probe_json(PROBE, ws, args=(str(data),), timeout=120)
        e2e, raw_e2e = probe_json(E2E, ws, timeout=60)
    if res is None:
        res = {name: ["probe crashed: " + raw.stderr[-300:]] for name in AREAS}
    def found(name):
        bad = res.get(name, [])
        return not bad, (f"{len(bad)} wrong: " + "; ".join(bad[:5]) if bad else "ok")

    g.add("weight-core", *found("weight-core"))
    g.add("rates-packing", *found("rates-packing"))
    g.add("carrier-limit", *found("carrier-limit"))
    g.add("validator", *found("validator"))
    g.add("cache-key", *found("cache-key"))
    g.add("storage", *found("storage"))
    g.add("export-stays-grams", *found("export-stays-grams"))
    g.add("text-output", *found("text-output"))
    g.add("reports", *found("reports"))
    cli = cli_problems(ws)
    g.add("cli-and-messages", not cli, "; ".join(cli[:4]) if cli else "ok")

    version = run_python("import shipcalc\nprint('@@RESULT ' + repr(shipcalc.__version__).replace(\"'\", '\"'))", ws)
    g.add("version-bumped", version.stdout.strip() == '@@RESULT "2.0.0"', f"version output {version.stdout.strip()!r} {version.stderr[-200:]!r}")
    log = changelog_problems(read_text(ws / "CHANGELOG.md"))
    g.add("changelog-entry-added", not log, "; ".join(log) if log else "ok")

    suite = subprocess.run([sys.executable, "-m", "unittest"], cwd=ws, capture_output=True, text=True, timeout=300,
                           env={**{k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ws)})
    g.add("full-test-suite-green", suite.returncode == 0, "unittest passes" if suite.returncode == 0 else suite.stderr[-300:])

    if e2e is None:
        g.add("end-to-end-consistency", False, "probe crashed: " + raw_e2e.stderr[-300:])
    else:
        g.add("end-to-end-consistency", not e2e, "; ".join(e2e) if e2e else "ok")
    names = gram_names(ws)
    g.add("no-gram-names-left", not names, "gram-named identifiers in migrated modules: " + "; ".join(names) if names else "ok", required=False)
    g.summary_checks(ws)


AREAS = {
    "weight-core": "units, Item and order totals",
    "rates-packing": "rates, parcels and quote",
    "carrier-limit": "overflow guard",
    "validator": "docstring-driven validator",
    "cache-key": "cache key",
    "storage": "storage schemas",
    "export-stays-grams": "csv and carrier payload",
    "text-output": "formatter",
    "reports": "reports",
}


if __name__ == "__main__":
    main(grade)
