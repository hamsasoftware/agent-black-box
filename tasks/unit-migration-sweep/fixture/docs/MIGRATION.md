# Migration: weights from grams to kilograms

shipcalc 2.0.0 stores and passes weights as **kilograms written as decimal strings** instead of whole grams. This page is the contract for the migration. Everything in the package that handles a weight follows it, except the formats listed under "What stays in grams".

## 1. Representation

A weight is a `str` in canonical form: one or more digits, a point, exactly three decimal places. Examples: `"0.250"`, `"12.000"`, `"1000.000"`. No sign, no exponent, no spaces, no float anywhere. Arithmetic uses `decimal.Decimal` or integers, never `float`.

`units.normalize_kg(value)` turns any accepted input into the canonical form (see 2 and 3).

## 2. Accepted input and rounding

Accepted input is a `str` of digits `0-9` with an optional point and at least one digit after it: `"2"`, `"1.5"`, `"0.250"`, `"1.2345"`. Input with more than three decimal places is rounded to three places, **half to even** (round half to even on the exact decimal value, not on a float): `"1.0005"` becomes `"1.000"`, `"1.0015"` becomes `"1.002"`, `"2.0025"` becomes `"2.002"`.

The same rounding applies to every computed weight that is not already exact (the average weight in 6).

## 3. Invalid input

Anything else is invalid: a leading sign (`"-1"`, `"+1"`), an exponent (`"1e3"`), `"nan"`, `"inf"`, an empty string, surrounding whitespace, a decimal comma (`"1,5"`), a trailing or leading point (`"1."`, `".5"`, `"."`), and any value that is not a `str` (`int`, `float`, `bool`, `None`, `Decimal`).

Invalid input is reported by raising `units.WeightError`, a subclass of `ValueError`. For invalid input its message is `invalid weight: ` followed by the `repr` of the offending value, for example `invalid weight: 'abc'` or `invalid weight: 1500`.

`WeightError` is also what reports a total over the carrier limit (see 5). The old `OverflowError` is no longer raised. The message of that error is free.

## 4. Renamed API

Old names are removed, not kept as aliases. Anything not listed keeps its name and behaviour.

| was | is |
|---|---|
| `units.to_grams(value)` | `units.normalize_kg(value) -> str`, plus `units.kg_to_g(value) -> int` and `units.g_to_kg(grams) -> str` (see below) |
| `Item(sku, weight_g, qty=1)`, `item.weight_g`, `item.to_dict()["weight_g"]` | `Item(sku, weight_kg, qty=1)`, `item.weight_kg` (canonical `str`), `item.to_dict()["weight_kg"]` |
| `item.line_weight_g()` | `item.line_weight_kg()` (canonical `str`) |
| `calc.order_weight_g(order)` | `calc.order_weight_kg(order)` (canonical `str`, `"0.000"` for an empty order) |
| `calc.quote(...)["weight_g"]` | `calc.quote(...)["weight_kg"]` (canonical `str`); `parcels` and `cents` are unchanged |
| `rates.shipping_cents(weight_g, zone)` | `rates.shipping_cents(weight_kg, zone)`; same costs |
| `Parcel.weight_g` | `Parcel.weight_kg` (canonical `str`) |
| `limits.check_total_g(grams)` | `limits.check_total_kg(weight_kg)`; returns the canonical weight |
| `format.format_weight(grams)` | `format.format_weight(weight_kg)` |
| `reports.average_weight_g(order)` | `reports.average_weight_kg(order)` (canonical `str`) |

`units.g_to_kg(grams)` takes a non-negative `int` (not a `bool`) and returns the canonical weight, so `g_to_kg(1250) == "1.250"`; anything else raises `WeightError`. `units.kg_to_g(value)` normalises `value` and returns the exact whole number of grams as an `int`, so `kg_to_g("1.25") == 1250`.

Every threshold keeps its meaning with the unit changed: 500 g is `0.500` kg, 20000 g is `20.000` kg, and so on. Comparisons that were `<=` or `>` stay `<=` or `>`. Costs in `rates` and the parcel packing order do not change.

## 5. Limits

- Order lines: the table in the `Item` docstring is the single source of the limits that `validate.validate_item` enforces. The weight line of the table becomes `weight_kg`, from `0.001` to `1000.000` kg (it was 1 to 1000000 g). `validate_item` reads the table, so the table and the code that parses it must both follow the new unit. The range applies **after** rounding: `"0.0004"` rounds to `"0.000"` and is out of range, `"1000.0004"` rounds to `"1000.000"` and is in range. A weight that is not valid input (section 3) is also reported as a problem on `weight_kg`. A problem is still a string that starts with the field name and a colon, for example `weight_kg: out of range 0.001..1000.000`. A dict that has `weight_g` but no `weight_kg` has a `weight_kg: missing` problem.
- Carrier limit: the carrier system still keeps a signed 32-bit number of grams. A total weight above `2147483.647` kg (that is 2**31 - 1 grams) is rejected with `WeightError`; exactly `2147483.647` kg is accepted. `calc.order_weight_kg` applies this limit.

## 6. Reports

`reports.average_weight_kg(order)` is the total weight divided by the number of units (sum of `qty`), rounded half to even to three places; `"0.000"` for an empty order (it was integer division). `heaviest` orders by weight as a number, heaviest first, ties by `sku`, as before. `weight_bands` keeps the same bands (a unit of at most 0.500 kg is `light`, at most 2.000 kg `medium`, else `heavy`).

## 7. Other call sites

- **Cache key**: `cache.quote_key(order, zone)` is `quote:v2:<zone>:<total>:<lines>` where `<total>` is the canonical total weight in kg and `<lines>` the number of order lines. The `v2` marks the unit change so that keys from before the migration are never mixed with new ones.
- **Text output**: `format_weight` returns the canonical weight followed by a space and `kg`, for example `0.250 kg` and `12.000 kg`, for every weight (there is no `g` form any more). The layout of `format_table` and of the `cli` output is unchanged.
- **Command line**: weight arguments of `add` are kilograms. A command that fails with a `ValueError` (including `WeightError`) prints `error: <message>` to standard error and exits with status 2, as before. `add` writes the new file format (below).
- **Storage**: `storage.save` writes `"schema": 2` and items with `"weight_kg"` (canonical string). `storage.load` reads schema 2, and still reads schema 1 files (items with integer `"weight_g"`), converting exactly. A schema 2 weight is normalised on load; an invalid weight in either schema raises `WeightError`; any other schema raises `ValueError` as before.

## What stays in grams

Two outputs are consumed by systems we do not own and keep whole grams. Their format does not change:

- `export.to_csv(order)`: header `sku,weight_g,qty`, and the per-unit weight of each item as an integer number of grams.
- `export.carrier_payload(order)`: `{"weight_g": <total as int grams>, "parcels": <count>}`.

Both must produce exact integers (`int`, not `float`, not a string).

## Housekeeping

- Bump `__version__` in `shipcalc/__init__.py` to `"2.0.0"` (the change is breaking).
- Add an entry to `CHANGELOG.md` under `## [Unreleased]`, in a `### Changed` section (create it if it is missing, keep the existing sections): a bullet that mentions `weight_kg` and says that weights are now kilograms.
