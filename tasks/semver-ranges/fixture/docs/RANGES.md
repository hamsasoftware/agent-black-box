# Version ranges

`depres` resolves dependency ranges written in the npm style. This page is the contract; the resolver and the lockfile checker both rely on it.

## Versions

Semantic versions `MAJOR.MINOR.PATCH`, optionally with a prerelease (`1.2.3-beta.2`) and build metadata (`1.2.3+build.5`, ignored for comparison). A leading `v` is allowed. `depres.version.Version` parses and orders them and is already correct.

## Ranges

A range is one or more **comparator sets** joined by `||`. A version satisfies the range if it satisfies any set. A comparator set is a whitespace-separated list of comparators; a version satisfies the set if it satisfies every comparator in it. An empty set (for example an empty string) matches every version.

Whitespace between an operator and its version is allowed: `>= 1.2.3` is the same as `>=1.2.3`.

### Primitive comparators

`<`, `<=`, `>`, `>=`, `=` followed by a version. No operator means `=`.

### Partial versions and X-ranges

`x`, `X` and `*` stand for "any" in a position, and missing positions count as `x`. So `*` and `""` match any release version (the prerelease rule below still applies to them), `1.x` and `1` mean `>=1.0.0 <2.0.0`, and `1.2.x` and `1.2` mean `>=1.2.0 <1.3.0`. A wildcard may not be followed by a number (`1.x.3` is invalid).

With an operator, partial versions mean:

| written | means |
|---|---|
| `>1` | `>=2.0.0` |
| `>1.2` | `>=1.3.0` |
| `>=1.2` | `>=1.2.0` |
| `<1.2` | `<1.2.0` |
| `<=1` | `<2.0.0` |
| `<=1.2` | `<1.3.0` |
| `=1.2` | `>=1.2.0 <1.3.0` |

### Hyphen ranges

`A - B` (spaces around the hyphen are required) means `>=A <=B`. A partial `A` fills missing positions with zeros. A partial `B` means "below the next": `1.2.3 - 2.3` is `>=1.2.3 <2.4.0` and `1.2.3 - 2` is `>=1.2.3 <3.0.0`.

### Tilde ranges

Allow patch-level changes if a minor version is given, minor-level changes if not.

- `~1.2.3` is `>=1.2.3 <1.3.0`
- `~1.2` is `>=1.2.0 <1.3.0`
- `~1` is `>=1.0.0 <2.0.0`
- `~1.2.3-beta.2` is `>=1.2.3-beta.2 <1.3.0`

### Caret ranges

Allow changes that do not modify the left-most non-zero part.

- `^1.2.3` is `>=1.2.3 <2.0.0`
- `^0.2.3` is `>=0.2.3 <0.3.0`
- `^0.0.3` is `>=0.0.3 <0.0.4`
- `^1.2` and `^1.2.x` are `>=1.2.0 <2.0.0`
- `^0.2` is `>=0.2.0 <0.3.0`, `^0.0` and `^0.0.x` are `>=0.0.0 <0.1.0`
- `^1` and `^1.x` are `>=1.0.0 <2.0.0`, `^0` and `^0.x` are `>=0.0.0 <1.0.0`

## Prereleases

A version with a prerelease tag satisfies a comparator set only if it satisfies every comparator **and** at least one comparator in the same set names the same `MAJOR.MINOR.PATCH` with a prerelease tag. So `>=1.2.3-alpha.1 <1.3.0` matches `1.2.3-alpha.7` but not `1.2.4-alpha.1`, and `^1.0.0` never matches `2.0.0-rc.1` or `1.5.0-beta`. The rule applies to every set, including `*` and the empty set: they name no prerelease, so `1.2.3-alpha` does not satisfy `*`.

## API

- `satisfies(version, range_) -> bool`
- `max_satisfying(versions, range_) -> str | None`: the highest version in the iterable that satisfies the range, returned exactly as given, or `None`.

Both raise `ValueError` for an invalid range or an invalid version.
