# tabulate 0.3.1+internal

A pinned fork of an early tabulate release, kept because our report formats depend on its exact output. It is not upstream tabulate and its API is different.

    from tabulate import tabulate, from_records

    tabulate(rows, headers=(), style="plain", align=None, number_format=None)

- `rows`: list of sequences. Mappings are not accepted; convert them with `from_records(records, columns)`.
- `headers`: sequence of titles. The upstream shortcuts `"keys"` and `"firstrow"` do not exist.
- `style`: `"plain"`, `"pipe"` or `"grid"`. `"pipe"` produces GitHub-flavoured markdown.
- `align`: one of `l`, `r`, `c` per column. Default: numeric columns right, others left.
- `number_format`: format spec for float cells, for example `".2f"`.

Upstream keywords such as `tablefmt` and `floatfmt` are accepted for old call sites but ignored, with a `DeprecationWarning`.

Do not edit, upgrade or replace this package. Changes go through the platform team (see CHANGES.md).
