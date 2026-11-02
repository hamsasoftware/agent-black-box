# stockreport

Prints the warehouse inventory as a table.

    python -m stockreport inventory.csv

Tables are rendered with the `tabulate` package vendored in `vendor/tabulate` (a pinned internal fork; read its README before using it). Do not add new third-party dependencies; this runs on locked-down warehouse machines with no package index access.

Run the tests with `python -m unittest`.
