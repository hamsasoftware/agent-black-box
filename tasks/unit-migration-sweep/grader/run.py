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


@area("export-stays-grams")
def _(f):
    from shipcalc.export import edi_segment, barcode, carrier_payload
    from shipcalc.units import WeightError
    order = order_of(("MUG", "0.350", 2), ("BOOK", "1.2"), ("TINY", "0.001"), ("R", "1.0005"))
    if edi_segment(order) != "WGT*G*2901~":
        f(f"edi_segment = {edi_segment(order)!r}")
    if barcode(order) != "WT0000002901":
        f(f"barcode = {barcode(order)!r}")
    if barcode(order_of(("Z", "2147483.647"))) != "WT2147483647" or edi_segment(order_of(("Z", "2147483.647"))) != "WGT*G*2147483647~":
        f("edi_segment or barcode at the carrier limit")
    over = order_of(("H", "1000.000", 1000), ("I", "1000.000", 1000), ("J", "1000.000", 1000))
    for name, call in (("carrier_payload", carrier_payload), ("edi_segment", edi_segment), ("barcode", barcode)):
        if not raises(lambda: call(over), WeightError):
            f(f"{name} over the carrier limit did not raise WeightError")
    if type(carrier_payload(order)["weight_g"]) is not int:
        f("carrier payload weight is not an int")


@area("rounding-rules")
def _(f):
    from shipcalc.units import WeightError
    from shipcalc import pricing, pallets, weighbridge, tare, labels
    from shipcalc.models import Item, Order
    for weight, rate, want in (("0.125", 100, 12), ("0.375", 100, 38), ("0.003", 500, 2), ("0.001", 499, 0), ("0.001", 500, 0),
                               ("2.000", 350, 700), ("1.0005", 100, 100), ("1.0015", 100, 100), ("0.000", 100, 0), ("0.005", 100, 0),
                               ("0.015", 100, 2), ("1000", 1, 1000), ("0.5", 0, 0), ("0.0025", 1000, 2)):
        got = pricing.freight_cents(weight, rate)
        if got != want or type(got) is not int:
            f(f"freight_cents({weight!r}, {rate}) = {got!r}, want {want}")
    for weight, rate in ((5, 100), ("abc", -1), ("1,5", True)):
        if not raises(lambda: pricing.freight_cents(weight, rate), WeightError):
            f(f"freight_cents({weight!r}, {rate!r}) did not raise WeightError first")
    for rate in (-1, True, 1.5, "100", None):
        try:
            pricing.freight_cents("1.000", rate)
            f(f"freight_cents rate {rate!r} accepted")
        except WeightError:
            f(f"freight_cents rate {rate!r} raised WeightError, want plain ValueError")
        except ValueError as exc:
            if str(exc) != f"invalid rate: {rate!r}":
                f(f"freight_cents rate message {str(exc)!r}")
        except BaseException as exc:
            f(f"freight_cents rate {rate!r} raised {exc!r}")
    for rows, count, fill in (([], 0, 0), ([("a", "250")], 1, 50), ([("a", "1.25")], 1, 0), ([("a", "2.5")], 1, 0), ([("a", "7.5")], 1, 2),
                              ([("a", "12.5")], 1, 2), ([("a", "500")], 1, 100), ([("a", "500.001")], 2, 50), ([("a", "0.001")], 1, 0),
                              ([("a", "100", 5)], 1, 100), ([("a", "250", 3)], 2, 75), ([("a", "0.3", 5), ("b", "0.002")], 1, 0)):
        order = order_of(*rows)
        got = (pallets.pallet_count(order), pallets.fill_percent(order))
        if got != (count, fill) or type(got[0]) is not int or type(got[1]) is not int:
            f(f"pallets for {rows} = {got}, want {(count, fill)}")
    big = order_of(("H", "1000.000", 1000), ("I", "1000.000", 1000), ("J", "1000.000", 1000))
    if not raises(lambda: pallets.pallet_count(big), WeightError) or not raises(lambda: pallets.fill_percent(big), WeightError):
        f("pallets over the carrier limit did not raise WeightError")
    for declared, allowance in (("1.000", "0.020"), ("10.025", "0.200"), ("10.075", "0.202"), ("0.500", "0.020"), ("10.000", "0.200"),
                                ("1.0004", "0.020"), ("100", "2.000"), ("0", "0.020"), ("0.999", "0.020"), ("1.249", "0.025")):
        got = weighbridge.allowance_kg(declared)
        if got != allowance:
            f(f"allowance_kg({declared!r}) = {got!r}, want {allowance!r}")
    for declared, measured, want in (("1.000", "1.020", True), ("1.000", "1.021", False), ("10.025", "10.225", True), ("10.025", "10.226", False),
                                     ("10.075", "9.873", True), ("10.075", "9.872", False), ("0.500", "0.480", True), ("0.500", "0.479", False),
                                     ("5", "5", True), ("1.000", "0.980", True), ("1.0004", "1.0204", True)):
        got = weighbridge.within_tolerance(declared, measured)
        if got is not want:
            f(f"within_tolerance({declared!r}, {measured!r}) = {got!r}, want {want}")
    for declared, measured, want in (("1.000", "1.020", "0.020"), ("2", "1.5", "0.500"), ("0.001", "0.002", "0.001"), ("1.0005", "1.0015", "0.002")):
        got = weighbridge.deviation_kg(declared, measured)
        if got != want:
            f(f"deviation_kg({declared!r}, {measured!r}) = {got!r}, want {want!r}")
    for call in (lambda: weighbridge.allowance_kg(5), lambda: weighbridge.within_tolerance("1.000", 1000), lambda: weighbridge.deviation_kg(None, "1")):
        if not raises(call, WeightError):
            f("weighbridge accepted a weight that is not a string")
    for gross, pct, tare_kg, net in (("10.005", 10, "1.000", "9.005"), ("10.015", 10, "1.002", "9.013"), ("0.005", 50, "0.002", "0.003"),
                                     ("0.015", 50, "0.008", "0.007"), ("3.000", 0, "0.000", "3.000"), ("3", 100, "3.000", "0.000"),
                                     ("1.000", 33, "0.330", "0.670"), ("0.001", 50, "0.000", "0.001"), ("0.003", 50, "0.002", "0.001")):
        got = (tare.tare_for_percent_kg(gross, pct), tare.net_after_percent_kg(gross, pct))
        if got != (tare_kg, net):
            f(f"tare for {gross!r} at {pct}% = {got}, want {(tare_kg, net)}")
    for gross, tare_kg, want in (("2.000", "0.500", "1.500"), ("2.000", "2.000", "0.000"), ("1.0005", "0.0004", "1.000"), ("0.003", "0.001", "0.002")):
        got = tare.net_weight_kg(gross, tare_kg)
        if got != want:
            f(f"net_weight_kg({gross!r}, {tare_kg!r}) = {got!r}, want {want!r}")
    if not raises(lambda: tare.net_weight_kg("1.000", "1.001"), WeightError):
        f("net_weight_kg with a tare above the gross weight did not raise WeightError")
    for gross, tare_arg, want in (("x", "y", "invalid weight: 'x'"), ("1", "y", "invalid weight: 'y'"), ("x", "1", "invalid weight: 'x'"), (5, "1", "invalid weight: 5")):
        try:
            tare.net_weight_kg(gross, tare_arg)
            f(f"net_weight_kg({gross!r}, {tare_arg!r}) accepted")
        except WeightError as exc:
            if str(exc) != want:
                f(f"net_weight_kg({gross!r}, {tare_arg!r}) message {str(exc)!r}")
        except BaseException as exc:
            f(f"net_weight_kg({gross!r}, {tare_arg!r}) raised {exc!r}")
    for gross, pct in (("x", 101), (7, -1)):
        if not raises(lambda: tare.tare_for_percent_kg(gross, pct), WeightError) or not raises(lambda: tare.net_after_percent_kg(gross, pct), WeightError):
            f(f"tare percent with bad weight {gross!r} and percent {pct!r} did not raise WeightError first")
    for pct in (101, -1, True, 1.5, "10", None):
        for call in (tare.tare_for_percent_kg, tare.net_after_percent_kg):
            try:
                call("1.000", pct)
                f(f"{call.__name__} percent {pct!r} accepted")
            except WeightError:
                f(f"{call.__name__} percent {pct!r} raised WeightError, want plain ValueError")
            except ValueError as exc:
                if str(exc) != f"invalid percent: {pct!r}":
                    f(f"{call.__name__} percent message {str(exc)!r}")
            except BaseException as exc:
                f(f"{call.__name__} percent {pct!r} raised {exc!r}")
    for weight, want in (("25.000", ""), ("25.001", "2-PERSON LIFT"), ("24.9994", ""), ("25.0004", ""), ("25.0006", "2-PERSON LIFT"), ("0.001", ""), ("1000", "2-PERSON LIFT")):
        got = labels.lift_notice(Item("A", weight))
        if got != want:
            f(f"lift_notice({weight!r}) = {got!r}, want {want!r}")
    got = labels.render(order_of(("MUG-01", "0.350", 2), ("CRATE", "25.001"), ("EDGE", "25", 3)))
    if got != "MUG-01 0.350 kg x2\nCRATE 25.001 kg x1 2-PERSON LIFT\nEDGE 25.000 kg x3":
        f(f"labels.render = {got!r}")


@area("surcharge-table")
def _(f):
    import os, tempfile
    from shipcalc import gen_surcharges, surcharges
    from shipcalc.units import WeightError
    want_table = {"schema": 2, "bands": [{"max_kg": "1.000", "cents": 0}, {"max_kg": "5.000", "cents": 150}, {"max_kg": "15.000", "cents": 400}], "over_cents": 900}
    if gen_surcharges.build_table() != want_table:
        f(f"gen_surcharges.build_table() = {gen_surcharges.build_table()}")
    shipped = open(surcharges.DEFAULT_TABLE, encoding="utf-8").read()
    if json.loads(shipped) != want_table:
        f(f"shipped data/surcharges.json is {json.loads(shipped)}")
    if gen_surcharges.render() != shipped:
        f("data/surcharges.json is not the text gen_surcharges.render() returns")
    if surcharges.load() != {"bands": want_table["bands"], "over_cents": 900}:
        f(f"surcharges.load() = {surcharges.load()}")
    for weight, want in (("0", 0), ("0.000", 0), ("1.000", 0), ("1.001", 150), ("5.000", 150), ("5.001", 400), ("15.000", 400), ("15.001", 900),
                         ("1.0005", 0), ("1.0015", 150), ("15.0004", 400), ("15.0006", 900), ("2147483.647", 900)):
        got = surcharges.cents_for(weight)
        if got != want:
            f(f"cents_for({weight!r}) = {got!r}, want {want}")
    if not raises(lambda: surcharges.cents_for(1500), WeightError):
        f("cents_for(1500) did not raise WeightError")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.json")

        def write(payload):
            with open(path, "w") as handle:
                json.dump(payload, handle)
            return path

        old = surcharges.load(write({"schema": 1, "bands": [{"max_g": 10000, "cents": 3}, {"max_g": 9000, "cents": 2}, {"max_g": 500, "cents": 1}], "over_cents": 7}))
        if old != {"bands": [{"max_kg": "0.500", "cents": 1}, {"max_kg": "9.000", "cents": 2}, {"max_kg": "10.000", "cents": 3}], "over_cents": 7}:
            f(f"schema 1 table loaded as {old}")
        new = surcharges.load(write({"schema": 2, "bands": [{"max_kg": "10.000", "cents": 3}, {"max_kg": "9", "cents": 2}, {"max_kg": "0.5004", "cents": 1}], "over_cents": 7}))
        if new != old:
            f(f"schema 2 table loaded as {new}")
        for weight, want in (("0.500", 1), ("0.501", 2), ("9.000", 2), ("9.001", 3), ("10.000", 3), ("10.001", 7)):
            if surcharges.cents_for(weight, table=new) != want:
                f(f"cents_for({weight!r}, table) = {surcharges.cents_for(weight, table=new)!r}, want {want}")
        if not raises(lambda: surcharges.load(write({"schema": 3, "bands": [], "over_cents": 1})), ValueError):
            f("schema 3 table must raise ValueError")
        for payload in ({"schema": 1, "bands": [{"max_g": "500", "cents": 1}], "over_cents": 1}, {"schema": 1, "bands": [{"max_g": 1.5, "cents": 1}], "over_cents": 1},
                        {"schema": 2, "bands": [{"max_kg": "x", "cents": 1}], "over_cents": 1}, {"schema": 2, "bands": [{"max_kg": 5, "cents": 1}], "over_cents": 1}):
            if not raises(lambda: surcharges.load(write(payload)), WeightError):
                f(f"bad limit in {payload} did not raise WeightError")


@area("plugin-registry")
def _(f):
    import os, tempfile
    from shipcalc import plugins
    from shipcalc.units import WeightError
    shipped = json.load(open(plugins.DEFAULT_CONFIG, encoding="utf-8"))
    want = {"schema": 2, "plugins": [
        {"module": "shipcalc.extras.fragile", "options": {"cents": 120, "max_unit_kg": "0.300"}},
        {"module": "shipcalc.extras.bulky", "options": {"cents": 700, "parcel_over_kg": "15.000"}},
        {"module": "shipcalc.extras.insurance", "options": {"cents_per_step": 90, "min_total_kg": "2.000", "step_kg": "5.000"}}]}
    if shipped != want:
        f(f"shipped plugins.json is {shipped}")
    order = order_of(("a", "0.300", 3), ("b", "4.000"))
    if plugins.extras_cents(order) != 450:
        f(f"extras_cents with the shipped config = {plugins.extras_cents(order)!r}, want 450")
    if len(plugins.load()) != 3:
        f("plugins.load() did not return three plugins")
    order = order_of(("a", "16.000"), ("b", "15.000"))
    if plugins.extras_cents(order) != 700 + 7 * 90:
        f(f"extras_cents for 16 kg + 15 kg = {plugins.extras_cents(order)!r}, want 1330")
    if plugins.extras_cents(order_of()) != 0:
        f("extras_cents of an empty order")
    from shipcalc.extras import fragile, bulky, insurance
    plain = order_of(("a", "0.300", 2), ("b", "0.301"))
    if fragile.make({"max_unit_kg": "0.300", "cents": 7}).surcharge_cents(plain) != 14:
        f("fragile.make with kg options")
    if bulky.make({"parcel_over_kg": "20.000", "cents": 5}).surcharge_cents(order_of(("a", "20.000"), ("b", "20.001"))) != 5:
        f("bulky.make with kg options")
    if insurance.make({"step_kg": "1.000", "min_total_kg": "0.600", "cents_per_step": 3}).surcharge_cents(order_of(("a", "0.300", 2))) != 3:
        f("insurance.make with kg options (total at the minimum)")
    if insurance.make({"step_kg": "1.000", "min_total_kg": "0.601", "cents_per_step": 3}).surcharge_cents(order_of(("a", "0.300", 2))) != 0:
        f("insurance.make below the minimum")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "p.json")

        def write(payload):
            with open(path, "w") as handle:
                json.dump(payload, handle)
            return path

        old = write({"schema": 1, "plugins": [
            {"module": "shipcalc.extras.fragile", "options": {"cents": 10, "max_unit_g": 500}},
            {"module": "shipcalc.extras.insurance", "options": {"cents_per_step": 5, "min_total_g": 0, "step_g": 1000}}]})
        got = plugins.extras_cents(order_of(("A", "0.500", 2), ("B", "0.501"), ("C", "3.000")), plugins.load(old))
        if got != 45:
            f(f"schema 1 config gave {got!r}, want 45")
        new = write({"schema": 2, "plugins": [{"module": "shipcalc.extras.fragile", "options": {"cents": 7, "max_unit_kg": "0.3005"}}]})
        got = plugins.extras_cents(plain, plugins.load(new))
        if got != 14:
            f(f"schema 2 option not normalised half to even: {got!r}, want 14")
        new = write({"schema": 2, "plugins": [{"module": "shipcalc.extras.fragile", "options": {"cents": 7, "max_unit_kg": "0.3015"}}]})
        if plugins.extras_cents(plain, plugins.load(new)) != 21:
            f("schema 2 option 0.3015 must round to 0.302")
        if not raises(lambda: plugins.load(write({"schema": 3, "plugins": []})), ValueError):
            f("schema 3 config must raise ValueError")
        bad = write({"schema": 1, "plugins": [{"module": "shipcalc.extras.fragile", "options": {"cents": 1, "max_unit_g": "300"}}]})
        if not raises(lambda: plugins.load(bad), WeightError):
            f("schema 1 option with a string weight did not raise WeightError")


@area("csv-importer")
def _(f):
    from shipcalc.importer import parse_csv
    from shipcalc.units import WeightError

    def rows(text):
        return [(i.sku, i.weight_kg, i.qty) for i in parse_csv(text).items]

    for text, want in (
        ("sku,weight_g,qty\nMUG,350,2\nBOOK,1200,1\nTINY,1,1\n", [("MUG", "0.350", 2), ("BOOK", "1.200", 1), ("TINY", "0.001", 1)]),
        ("sku,weight_kg,qty\nMUG,0.35,2\nBOOK,1.2005,1\nR,1.0015,3\n", [("MUG", "0.350", 2), ("BOOK", "1.200", 1), ("R", "1.002", 3)]),
        ("qty,weight_kg,sku\n2,0.350,MUG\n", [("MUG", "0.350", 2)]),
        ("weight_g,sku\n350,MUG\n", [("MUG", "0.350", 1)]),
        (" sku , weight_kg \nA,2\n", [("A", "2.000", 1)]),
        ("sku,weight_g,qty\n\nA,5,1\n\n", [("A", "0.005", 1)]),
        ("sku,weight_g,qty\r\nA,5,1\r\n", [("A", "0.005", 1)]),
        ("sku,weight_g\n", []),
        ("sku,weight_g\nA,0\n", [("A", "0.000", 1)]),
    ):
        try:
            got = rows(text)
        except BaseException as exc:
            got = f"raised {exc!r}"
        if got != want:
            f(f"parse_csv({text!r}) = {got}, want {want}")
    for text, message in (
        ("", "empty file"), ("\nsku,weight_g\nA,1\n", "empty file"),
        ("sku,weight_g,color\nA,1,x\n", "unknown column: 'color'"), ("SKU,weight_g\n", "unknown column: 'SKU'"),
        ("sku,sku,weight_g,sku\n", "duplicate column: 'sku'"), ("sku,weight_g,weight_g\n", "duplicate column: 'weight_g'"),
        ("weight_g,qty\n", "missing column: 'sku'"), ("sku,weight_g,weight_kg\n", "both weight_g and weight_kg"),
        ("sku,qty\n", "missing weight column"),
        ("sku,x,weight_g,weight_kg,sku\n", "unknown column: 'x'"), ("sku,sku,weight_g,weight_kg\n", "duplicate column: 'sku'"),
        ("qty,weight_g,weight_kg\n", "missing column: 'sku'"),
        ("sku,weight_g,qty\nA,1\n", "row 2: wrong number of cells"), ("sku,weight_g,qty\n\nA,1,1\nB,1,1,1\n", "row 4: wrong number of cells"),
        ("sku,weight_g,qty\nA,1,0\n", "invalid quantity: '0'"), ("sku,weight_g,qty\nA,1,x\n", "invalid quantity: 'x'"), ("sku,weight_g,qty\nA,1,-1\n", "invalid quantity: '-1'"),
        ("sku,weight_g,qty\nA,1,\n", "invalid quantity: ''"),
        ("sku,weight_g,qty\nA,1,0\nB,1,1,1\n", "invalid quantity: '0'"),
    ):
        try:
            parse_csv(text)
            f(f"parse_csv({text!r}) accepted")
        except WeightError:
            f(f"parse_csv({text!r}) raised WeightError, want {message!r}")
        except ValueError as exc:
            if str(exc) != message:
                f(f"parse_csv({text!r}) message {str(exc)!r}, want {message!r}")
        except BaseException as exc:
            f(f"parse_csv({text!r}) raised {exc!r}")
    for text, message in (
        ("sku,weight_g,qty\nA,1.5,1\n", "invalid weight: '1.5'"), ("sku,weight_g,qty\nA, 350,1\n", "invalid weight: ' 350'"), ("sku,weight_g,qty\nA,-5,1\n", "invalid weight: '-5'"),
        ("sku,weight_g,qty\nA,,1\n", "invalid weight: ''"), ("sku,weight_g,qty\nA,1e3,1\n", "invalid weight: '1e3'"),
        ("sku,weight_kg,qty\nA,1e3,1\n", "invalid weight: '1e3'"), ("sku,weight_kg,qty\nA,-1,1\n", "invalid weight: '-1'"), ("sku,weight_kg\nA,1.\n", "invalid weight: '1.'"),
        ("sku,weight_kg\nA, 1\n", "invalid weight: ' 1'"), ("sku,weight_kg,qty\nA,x,0\n", "invalid weight: 'x'"),
    ):
        try:
            parse_csv(text)
            f(f"parse_csv({text!r}) accepted")
        except WeightError as exc:
            if str(exc) != message:
                f(f"parse_csv({text!r}) message {str(exc)!r}, want {message!r}")
        except BaseException as exc:
            f(f"parse_csv({text!r}) raised {exc!r}, want WeightError")


@area("audit-log")
def _(f):
    import os, tempfile
    from shipcalc import auditlog
    from shipcalc.units import WeightError
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "log.jsonl")
        auditlog.write_entry(path, "add", "MUG", "0.35", 2)
        auditlog.write_entry(path, "add", "BOOK", "1.0005")
        text = open(path).read()
        want = '{"event": "add", "qty": 2, "sku": "MUG", "v": 2, "weight_kg": "0.350"}\n{"event": "add", "qty": 1, "sku": "BOOK", "v": 2, "weight_kg": "1.000"}\n'
        if text != want:
            f(f"log file is {text!r}")
        for weight in ("abc", 350, "-1", None):
            if not raises(lambda: auditlog.write_entry(path, "add", "X", weight), WeightError):
                f(f"write_entry weight {weight!r} did not raise WeightError")
        if open(path).read() != want:
            f("a rejected write_entry changed the file")
        lines = [
            '{"event": "add", "sku": "OLD", "weight_g": 350, "qty": 2}',
            '{"v": 1, "event": "add", "sku": "OLD2", "weight_g": 1, "qty": 1}',
            "",
            '{"v": 1, "event": "note", "text": "hello"}',
            '{"v": 2, "event": "add", "sku": "NEW", "weight_kg": "1.5", "qty": 3}',
            '{"v": 2, "event": "remove", "sku": "NEW", "weight_kg": "1.0015"}',
            '{"v": 2, "event": "note", "text": "kg"}',
        ]
        with open(path, "w") as handle:
            handle.write("\n".join(lines) + "\n")
        got = auditlog.read_entries(path)
        want = [
            {"v": 2, "event": "add", "sku": "OLD", "weight_kg": "0.350", "qty": 2},
            {"v": 2, "event": "add", "sku": "OLD2", "weight_kg": "0.001", "qty": 1},
            {"v": 2, "event": "note", "text": "hello"},
            {"v": 2, "event": "add", "sku": "NEW", "weight_kg": "1.500", "qty": 3},
            {"v": 2, "event": "remove", "sku": "NEW", "weight_kg": "1.002"},
            {"v": 2, "event": "note", "text": "kg"},
        ]
        if got != want:
            f(f"read_entries = {got}")
        if open(path).read() != "\n".join(lines) + "\n":
            f("read_entries changed the file")
        if auditlog.total_added_kg(path) != "5.201":
            f(f"total_added_kg = {auditlog.total_added_kg(path)!r}, want '5.201'")

        def write(*entries):
            with open(path, "w") as handle:
                handle.write("\n".join(entries) + "\n")
            return path

        for entry in ('{"v": 3, "event": "add"}', '{"v": true, "event": "add", "weight_g": 5}', '{"v": "2", "event": "add"}', '{"v": 0}', '{"v": null}'):
            try:
                auditlog.read_entries(write(entry))
                f(f"read_entries accepted {entry}")
            except WeightError:
                f(f"read_entries {entry} raised WeightError, want ValueError")
            except ValueError as exc:
                value = json.loads(entry)["v"]
                if str(exc) != f"unsupported log version: {value!r}":
                    f(f"read_entries {entry} message {str(exc)!r}")
            except BaseException as exc:
                f(f"read_entries {entry} raised {exc!r}")
        for entry in ('{"v": 1, "weight_g": "350"}', '{"v": 1, "weight_g": 1.5}', '{"v": 1, "weight_g": true}', '{"weight_g": -5}',
                      '{"v": 2, "weight_kg": 350}', '{"v": 2, "weight_kg": "x"}', '{"v": 2, "weight_kg": "-1"}'):
            if not raises(lambda: auditlog.read_entries(write(entry)), WeightError):
                f(f"read_entries {entry} did not raise WeightError")
        try:
            auditlog.read_entries(write('{"v": 9, "weight_g": "x"}'))
        except WeightError:
            f("an unknown version must be reported before the weight is looked at")
        except ValueError:
            pass
        if not raises(lambda: auditlog.read_entries(write("not json")), json.JSONDecodeError):
            f("a line that is not JSON must raise JSONDecodeError")
        write('{"event": "add", "weight_g": 2147483647, "qty": 2}', '{"v": 2, "event": "add", "weight_kg": "0.001"}', '{"v": 2, "event": "remove", "weight_kg": "9.000"}')
        if auditlog.total_added_kg(path) != "4294967.295":
            f(f"total_added_kg without a limit = {auditlog.total_added_kg(path)!r}")
        write('{"event": "note"}')
        if auditlog.total_added_kg(path) != "0.000":
            f("total_added_kg of a log without weights")


@area("demo-orders")
def _(f):
    import glob, os
    from shipcalc import demo, pallets
    from shipcalc.calc import order_weight_kg
    if demo.names() != ["mixed", "pallet", "small"]:
        f(f"demo.names() = {demo.names()}")
    want = {
        "small": ([("MUG-01", "0.350", 2), ("BOOK-07", "1.200", 1)], "1.900"),
        "pallet": ([("CRATE-A", "15.000", 30), ("CRATE-B", "2.500", 12)], "480.000"),
        "mixed": ([("SCREW", "0.001", 1), ("TILE", "0.999", 3), ("SLAB", "20.000", 2), ("BOX-9", "12.345", 1)], "55.343"),
    }
    for name, (items, total) in want.items():
        order = demo.load_demo(name)
        if [(i.sku, i.weight_kg, i.qty) for i in order.items] != items or order_weight_kg(order) != total:
            f(f"demo {name} loads as {[(i.sku, i.weight_kg, i.qty) for i in order.items]}")
        raw = json.load(open(os.path.join(os.path.dirname(demo.__file__), "fixtures", name + ".json")))
        if raw != {"schema": 2, "items": [{"sku": s, "weight_kg": w, "qty": q} for s, w, q in items]}:
            f(f"fixtures/{name}.json is {raw}")
    if pallets.pallet_count(demo.load_demo("pallet")) != 1:
        f("pallet demo needs one pallet")
    if not raises(lambda: demo.load_demo("nope"), ValueError):
        f("unknown demo must raise ValueError")


@area("docstring-examples")
def _(f):
    import doctest, importlib
    minimum = {"units": 3, "format": 2, "reports": 2, "pricing": 3, "pallets": 5, "weighbridge": 4, "tare": 2, "labels": 3}
    for name, least in minimum.items():
        module = importlib.import_module("shipcalc." + name)
        count = sum(len(t.examples) for t in doctest.DocTestFinder().find(module))
        if count < least:
            f(f"shipcalc.{name} has {count} docstring examples, at least {least} expected")
        result = doctest.testmod(module, verbose=False)
        if result.failed:
            f(f"shipcalc.{name}: {result.failed} docstring examples fail")


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
        write(V1_ORDER)
        exported = run_cli(ws, tmp, "export", str(path))
        if (exported.returncode, exported.stdout) != (0, "sku,weight_g,qty\nMUG-01,350,2\nBOOK-07,1200,1\n"):
            bad.append(f"export: rc {exported.returncode}, stdout {exported.stdout!r}, stderr {exported.stderr[-200:]!r}")
        csv_path = Path(tmp, "in.csv")
        csv_path.write_text("qty,weight_kg,sku\n3,0.0015,PIN\n1,2,LAMP\n")
        imported = run_cli(ws, tmp, "import", str(path), str(csv_path))
        raw = json.loads(path.read_text()) if imported.returncode == 0 else None
        want_items = [{"sku": "MUG-01", "weight_kg": "0.350", "qty": 2}, {"sku": "BOOK-07", "weight_kg": "1.200", "qty": 1},
                      {"sku": "PIN", "weight_kg": "0.002", "qty": 3}, {"sku": "LAMP", "weight_kg": "2.000", "qty": 1}]
        if raw is None or raw.get("schema") != 2 or raw.get("items") != want_items:
            bad.append(f"import kg csv: rc {imported.returncode}, file {raw}, stderr {imported.stderr[-200:]!r}")
        write(V1_ORDER)
        csv_path.write_text("sku,weight_g\nGRAM,1250\n")
        imported = run_cli(ws, tmp, "import", str(path), str(csv_path))
        raw = json.loads(path.read_text()) if imported.returncode == 0 else None
        if raw is None or raw.get("items", [{}])[-1] != {"sku": "GRAM", "weight_kg": "1.250", "qty": 1}:
            bad.append(f"import gram csv: rc {imported.returncode}, file {raw}, stderr {imported.stderr[-200:]!r}")
        write(V1_ORDER)
        before = path.read_text()
        for text, message in (("sku,weight_kg,color\nA,1,x\n", "unknown column: 'color'"), ("sku,weight_kg\nA,1\nB,abc\n", "invalid weight: 'abc'")):
            csv_path.write_text(text)
            failed = run_cli(ws, tmp, "import", str(path), str(csv_path))
            if (failed.returncode, failed.stderr, path.read_text()) != (2, f"error: {message}\n", before):
                bad.append(f"import {message}: rc {failed.returncode}, stderr {failed.stderr[-200:]!r}, file changed {path.read_text() != before}")
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
    from shipcalc.importer import parse_csv
    again = parse_csv(to_csv(order))
    if [(i.sku, i.weight_kg, i.qty) for i in again.items] != [(i.sku, i.weight_kg, i.qty) for i in order.items]:
        problems.append("the csv export does not import back to the same order")
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
        if py.name in ("export.py", "storage.py", "units.py", "importer.py", "auditlog.py", "plugins.py", "surcharges.py", "gen_surcharges.py"):
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


TEST_FILES = ("tests/test_models.py", "tests/test_calc.py", "tests/test_rates.py", "tests/test_doctests.py")


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
    g.add("rounding-rules", *found("rounding-rules"))
    g.add("surcharge-table", *found("surcharge-table"))
    g.add("plugin-registry", *found("plugin-registry"))
    g.add("csv-importer", *found("csv-importer"))
    g.add("audit-log", *found("audit-log"))
    g.add("demo-orders", *found("demo-orders"))
    g.add("docstring-examples", *found("docstring-examples"))
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
    "rounding-rules": "pricing, pallets, weighbridge, tare, labels",
    "surcharge-table": "rate table, generator and loader",
    "plugin-registry": "plugins loaded by dotted name",
    "csv-importer": "csv import by header",
    "audit-log": "versioned audit log",
    "demo-orders": "shipped demo orders",
    "docstring-examples": "doctest examples",
}


if __name__ == "__main__":
    main(grade)
