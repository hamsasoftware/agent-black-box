# Files, imports and logs: new formats and reading old data

Companion to `docs/MIGRATION.md`. The package writes the new formats only, and keeps reading the old ones where this page says so. Weights in the new formats are canonical kilogram strings (MIGRATION.md section 1).

## Reading old data: the rules

1. A reader converts old data exactly: whole grams to kilograms with `units.g_to_kg`. Nothing is rounded, because a gram is exactly 0.001 kg.
2. Old data is only read, never rewritten by a reader. Writers always write the new format.
3. The version of a file or entry decides how it is read; the shape of the weight does not.
4. A weight that is not valid in its version raises `WeightError` (message `invalid weight: ` plus the `repr` of the value). In old formats a valid weight is a non-negative `int` that is not a `bool`; in new formats it is valid input in the sense of MIGRATION.md section 3 (a string), and it is normalised.
5. A version that no reader knows is a `ValueError`, checked before any weight is looked at.

## Order files (`storage`)

Schema 1 (grams, `"weight_g"` integers) is read; schema 2 (`"weight_kg"` strings) is written and read; anything else is `ValueError: unsupported schema: <repr>`. See MIGRATION.md section 7.

## CSV import: `importer.parse_csv(text) -> Order`

The first line is the header. Header names are separated by commas and stripped of surrounding spaces; they are case sensitive. Allowed names are `sku`, `weight_g`, `weight_kg` and `qty`, in any order. A file has exactly one weight column, `weight_g` (old files, whole grams) or `weight_kg` (new files, kilograms), and a `qty` column is optional (a missing one means quantity 1 for every row). The cells of a row are found by header name.

Problems with the header are reported with `ValueError`; when several apply, the first in this list is reported:

1. no lines, or an empty first line: `empty file`
2. a name that is not allowed (the first one, left to right): `unknown column: <repr of the name>`
3. a name that appears twice (the second occurrence): `duplicate column: <repr>`
4. no `sku` column: `missing column: 'sku'`
5. both weight columns: `both weight_g and weight_kg`
6. no weight column: `missing weight column`

Rows follow the header. Lines end with `\n` or `\r\n` (the last line may have no line end). Rows are split at every comma (there is no quoting) and cells are not stripped. An empty line is skipped. Lines are numbered from 1, the header being line 1, and empty lines count. For each row the first of these problems is reported:

1. a different number of cells than the header: `ValueError` with message `row <line number>: wrong number of cells`
2. a weight that is not valid for its column: `WeightError` with message `invalid weight: ` plus the `repr` of the cell (a string). In a `weight_g` column a valid cell is one or more digits `0-9` and nothing else, converted exactly; in a `weight_kg` column a valid cell is valid input in the sense of MIGRATION.md section 3, rounded half to even
3. a quantity that is not one or more digits, or is 0: `ValueError` with message `invalid quantity: ` plus the `repr` of the cell

Rows are processed from the top; the first problem found stops the import. The `sku` cell is taken as it is. The text written by `export.to_csv` (grams) is accepted, and so is the same table with a `weight_kg` column.

## Audit log: `auditlog`

A log file has one JSON object per line. Blank lines are skipped. Version 1 entries (the first logs had no `v` field at all, which also means version 1) look like `{"event": "add", "qty": 2, "sku": "MUG-01", "v": 1, "weight_g": 350}`; version 2 entries look like `{"event": "add", "qty": 2, "sku": "MUG-01", "v": 2, "weight_kg": "0.350"}`.

- `write_entry(path, event, sku, weight_kg, qty=1)` normalises the weight first (invalid: `WeightError`, and the file is not touched), then appends one version 2 line to the file, written with `json.dumps(entry, sort_keys=True)`.
- `read_entries(path)` returns a list of dicts, one per entry, all in the current shape: `v` is 2 and the weight, when the entry has one, is under `weight_kg` as a canonical string (a version 1 `weight_g` is converted and the `weight_g` key is removed). All other keys are passed through unchanged. An entry without any weight (for example a `note` event) only gets `v` set to 2. The version is the integer 1 or 2 (`true` and `"2"` are not versions); a missing `v` means 1; anything else is `ValueError` with message `unsupported log version: ` plus the `repr` of the value. A line that is not valid JSON raises the `json.JSONDecodeError` as it is. Entries are checked in file order and the first problem stops the read.
- `total_added_kg(path)` is the sum of weight times `qty` (1 when missing) over the entries whose `event` is `add` and that have a weight, as a canonical string; it is computed from the converted entries of `read_entries` and has no upper limit.

## Rate table: `data/surcharges.json`, `surcharges.load`, `gen_surcharges`

The rate table is generated by `shipcalc/gen_surcharges.py`; the data file is exactly the text `gen_surcharges.render()` returns (`json.dumps(table, indent=2, sort_keys=True)` plus a newline), and `build_table()` returns the table it describes. After the migration it is schema 2: `{"schema": 2, "bands": [{"max_kg": "1.000", "cents": 0}, ...], "over_cents": 900}`, with the same limits and amounts as today (1.000, 5.000 and 15.000 kg). Schema 1 uses `"max_g"` integers.

`surcharges.load(path=None)` reads the shipped file or the given file, schema 1 or 2, and always returns `{"bands": [{"max_kg": <canonical str>, "cents": <int>}, ...], "over_cents": <int>}` with the bands sorted by limit **as numbers** (the order in the file does not matter; `"10.000"` comes after `"9.000"`). Any other schema is `ValueError: unsupported schema: <repr>`. A bad limit is a `WeightError`.

## Plugins: `plugins.json`, `plugins.load`, `plugins.extras_cents`

`shipcalc/plugins.json` lists the plugins to load: `{"schema": 1, "plugins": [{"module": "shipcalc.extras.fragile", "options": {...}}, ...]}`. The registry imports each module by the dotted name in the file (`importlib`), calls its `make(options)` and keeps the plugins in file order. `extras_cents(order, plugins=None)` is the sum of `plugin.surcharge_cents(order)` over the given plugins, or over `load()` when none are given.

- Schema 1 options carry weights as whole grams under keys ending in `_g` (`max_unit_g`, `parcel_over_g`, `step_g`, `min_total_g`). Schema 2 options carry them as canonical kilogram strings under keys ending in `_kg`.
- `plugins.load` always hands `make` options in the schema 2 form: when it reads a schema 1 file, every key ending in `_g` becomes the key ending in `_kg` with the value converted exactly (a value that is not a valid gram weight is a `WeightError`); in a schema 2 file the values of keys ending in `_kg` are normalised. Other options (`cents`, `cents_per_step`) are passed unchanged. Any other schema is `ValueError: unsupported schema: <repr>`.
- The shipped file is migrated to schema 2 with the same values: fragile `max_unit_kg` `"0.300"`, bulky `parcel_over_kg` `"15.000"`, insurance `step_kg` `"5.000"` and `min_total_kg` `"2.000"`.
- A plugin's `make(options)` receives schema 2 options (weights as canonical strings under `_kg` keys).

## Demo orders: `shipcalc/fixtures/*.json`, `demo`

The demo orders `small`, `mixed` and `pallet` are order files in the format of `storage`. After the migration they are schema 2 files with the same items in the same order and exactly the same weights. `demo.names()` is the sorted list of the file names without `.json`; `demo.load_demo(name)` loads one with `storage.load` and raises `ValueError: unknown demo: <repr>` for another name.
