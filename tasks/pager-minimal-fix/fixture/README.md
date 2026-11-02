# shopapi

Catalogue export for the storefront. `python -m shopapi export` writes every product as CSV to standard output.

- `generated/catalog_client.py` is generated from the catalogue service's OpenAPI document. Never edit it by hand.
- `legacy/` belongs to the finance team (see `OWNERS`).

Run the tests with `python -m unittest`.
