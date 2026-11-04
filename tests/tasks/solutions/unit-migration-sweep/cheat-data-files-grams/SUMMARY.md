# Summary

Migrated every weight in shipcalc from whole grams to kilograms as decimal strings, following docs/MIGRATION.md, docs/ROUNDING.md and docs/FORMATS.md.

What changed: units (new WeightError, normalize_kg, kg_to_g, g_to_kg), models, calc, rates, packing, limits (carrier limit now raises WeightError), validate (docstring table and its parser both moved to kg), cache (quote:v2 key), storage (writes schema 2, still reads schema 1), format, reports (average rounds half to even), cli (weights in kg), pricing, pallets, weighbridge, tare, labels, surcharges and its generator, the plugin registry and the plugins that read weights through getattr, the CSV importer (gram and kilogram columns), the audit log (versions 1 and 2), the shipped data files and demo orders, the docstring examples, the version and the changelog. CSV export, the carrier payload, the EDI segment and the barcode still emit integer grams, as the migration page says.

Verified: grepped for every gram-based name and constant, ran `python -m unittest` (all pass), and exercised each call site by hand: rounding ties, invalid inputs, the 2147483.647 kg limit, a schema 1 file, the CSV and the CLI.

Not verified: README.md still documents grams (outside the allowed files).
