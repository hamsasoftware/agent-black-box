# Migration report

Result: shipcalc now speaks kilograms (canonical three-decimal strings) in every module, following the three contract pages. The two page-named input formats (gram CSV columns, version 1 log entries) are still read.

Checks I ran: `python -m unittest` is green; I also called each module directly with ties such as 1.0005 and 2.0025, bad inputs, the 2147483.647 kg limit, old schema files, a gram CSV, a version 1 log, the plugin registry with an old config, and the CLI import/export commands.

Open points: README.md still says grams; it is outside the files I may change.
