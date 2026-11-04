# Computed quantities, rounding and boundaries

Companion to `docs/MIGRATION.md`. It defines every quantity the package computes from a weight, how it is rounded and where the boundaries lie. Weights are canonical kilogram strings (MIGRATION.md section 1).

## General rules

1. **Input first.** Every weight argument is first turned into the canonical form with `units.normalize_kg` (so `"1.0005"` becomes `"1.000"`), and every computation starts from the normalised value. An invalid weight raises `WeightError` before anything else is looked at.
2. **Round once.** A computed value is the exact result on the normalised inputs, rounded half to even once, at the end. Never round an intermediate value.
3. **Types.** Weights are canonical `str`. Amounts of money (cents), counts and percentages are `int`. Booleans are not integers anywhere.
4. **Order of errors.** When several arguments are wrong, the first one in this order is reported: weight arguments in the order of the signature (`WeightError`), then the other arguments in the order of the signature (plain `ValueError`), then a rule of the quantity itself.
5. **Ties.** "Half to even" means: an exact tie goes to the neighbour whose last kept digit is even. Worked examples are given for each quantity.

## Freight: `pricing.freight_cents(weight_kg, cents_per_kg)`

The cost in whole cents is `weight_kg * cents_per_kg`, rounded half to even to a whole number. `cents_per_kg` is a non-negative `int` (not a `bool`); otherwise `ValueError` with the message `invalid rate: ` followed by the `repr` of the value (the weight is checked first).

| weight_kg | cents_per_kg | exact | result |
|---|---|---|---|
| `"0.125"` | 100 | 12.5 | 12 |
| `"0.375"` | 100 | 37.5 | 38 |
| `"0.003"` | 500 | 1.5 | 2 |
| `"0.001"` | 499 | 0.499 | 0 |
| `"2.000"` | 350 | 700 | 700 |
| `"1.0005"` | 100 | weight is `"1.000"` first | 100 |
| `"1.0015"` | 100 | weight is `"1.002"` first | 100 (100.2) |

## Pallets: `pallets.pallet_count(order)` and `pallets.fill_percent(order)`

A pallet carries at most 500.000 kg. `pallet_count` is the number of pallets needed for the total weight of the order (`calc.order_weight_kg`, so the carrier limit applies): the total divided by 500 and rounded up; 0 for an empty order. Exactly 500.000 kg needs 1 pallet, 500.001 kg needs 2.

`fill_percent` is the total divided by the combined capacity (`pallet_count * 500` kg) times 100, rounded half to even to a whole `int`; 0 for an empty order.

| total | pallets | exact fill | `fill_percent` |
|---|---|---|---|
| 250.000 | 1 | 50 | 50 |
| 1.250 | 1 | 0.25 | 0 |
| 2.500 | 1 | 0.5 | 0 |
| 7.500 | 1 | 1.5 | 2 |
| 12.500 | 1 | 2.5 | 2 |
| 500.000 | 1 | 100 | 100 |
| 500.001 | 2 | 50.0001 | 50 |

## Weighbridge: `weighbridge.allowance_kg`, `deviation_kg`, `within_tolerance`

`allowance_kg(declared_kg)` is the larger of 0.020 kg and 2 percent of the declared weight (rounded half to even to three places), as a canonical string. `deviation_kg(declared_kg, measured_kg)` is the absolute difference as a canonical string. `within_tolerance(declared_kg, measured_kg)` is true when the deviation is **at most** the allowance (a deviation equal to the allowance is within tolerance).

| declared | 2 percent exact | `allowance_kg` | measured | within? |
|---|---|---|---|---|
| `"1.000"` | 0.020 | `"0.020"` | `"1.020"` | yes |
| `"1.000"` | 0.020 | `"0.020"` | `"1.021"` | no |
| `"10.025"` | 0.2005 | `"0.200"` | `"10.225"` | yes |
| `"10.025"` | 0.2005 | `"0.200"` | `"10.226"` | no |
| `"10.075"` | 0.2015 | `"0.202"` | `"9.873"` | yes |
| `"0.500"` | 0.010 | `"0.020"` | `"0.480"` | yes |

## Tare: `tare.net_weight_kg`, `tare.tare_for_percent_kg`, `tare.net_after_percent_kg`

- `tare_for_percent_kg(gross_kg, percent)`: `percent` percent of the gross weight, rounded half to even to three places, canonical string. `percent` is an `int` from 0 to 100 (not a `bool`), otherwise `ValueError` with the message `invalid percent: ` followed by the `repr` (the weight is checked first).
- `net_after_percent_kg(gross_kg, percent)`: the gross weight minus the rounded tare above, canonical string.
- `net_weight_kg(gross_kg, tare_kg)`: the difference, canonical string. The gross weight is checked before the tare. A tare above the gross weight raises `WeightError` (any message); a tare equal to the gross weight gives `"0.000"`.

| gross | percent | exact tare | `tare_for_percent_kg` | `net_after_percent_kg` |
|---|---|---|---|---|
| `"10.005"` | 10 | 1.0005 | `"1.000"` | `"9.005"` |
| `"10.015"` | 10 | 1.0015 | `"1.002"` | `"9.013"` |
| `"0.005"` | 50 | 0.0025 | `"0.002"` | `"0.003"` |
| `"0.015"` | 50 | 0.0075 | `"0.008"` | `"0.007"` |
| `"3.000"` | 0 | 0 | `"0.000"` | `"3.000"` |

## Labels: `labels.lift_notice(item)`, `labels.label(item)`

A unit that weighs **more than** 25.000 kg needs a two-person lift: `lift_notice` returns `"2-PERSON LIFT"` for it and `""` otherwise (exactly 25.000 kg is not heavy). `label(item)` is `<sku> <format_weight(weight)> x<qty>`, followed by a space and the notice when there is one: `MUG-01 0.350 kg x2`, `CRATE 25.001 kg x1 2-PERSON LIFT`. `render(order)` joins the labels with newlines.

## Surcharge bands: `surcharges.cents_for(weight_kg, table=None)`

The first band (bands are in ascending order of limit, compared as numbers) whose limit is **at least** the weight applies; a weight above every limit gets `over_cents`. The weight is normalised first. With the shipped table (limits 1.000, 5.000, 15.000 kg; 0, 150, 400 cents; over 900): 1.000 kg costs 0, 1.001 kg costs 150, 15.000 kg costs 400, 15.001 kg costs 900.

## Plugin surcharges (see FORMATS.md for the configuration)

- `fragile`: `cents` for every unit (`qty` counts) whose weight is **at most** `max_unit_kg`.
- `bulky`: `cents` for every parcel from `packing.split_parcels` whose weight is **more than** `parcel_over_kg`.
- `insurance`: 0 when the total weight (`calc.order_weight_kg`) is **less than** `min_total_kg`; otherwise `cents_per_step` for every started step of `step_kg` (the total divided by the step, rounded up).

With the shipped configuration (fragile 0.300 kg and 120 cents; bulky 15.000 kg and 700 cents; insurance step 5.000 kg, minimum 2.000 kg, 90 cents) the order of three units of 0.300 kg and one of 4.000 kg totals 4.900 kg: fragile 360, bulky 0, insurance 90.
