# Changelog

## [Unreleased]

### Added

- `reports.weight_bands` counts units per weight band.

### Changed

- Weights are now kilograms written as decimal strings (`weight_kg`, e.g. `"0.250"`) instead of whole grams. See docs/MIGRATION.md. CSV export and the carrier payload stay in grams.

## [1.4.2] - 2026-09-12

### Fixed

- `packing.split_parcels` no longer drops a unit that is exactly at the parcel limit.

## [1.4.1] - 2026-08-30

### Fixed

- `cli quote` prints cents with two digits.
