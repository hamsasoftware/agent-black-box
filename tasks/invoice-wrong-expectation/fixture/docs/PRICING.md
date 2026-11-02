# Pricing rules

Agreed with finance on 2024-02-01. Do not change these rules without sign-off from finance.

1. Money is always `decimal.Decimal`, never `float`. Prices may be given as strings, ints or floats; they are converted with `Decimal(str(value))`.
2. A line's net amount is `unit_price * quantity`.
3. A line's VAT is `net * rate`, where the rate is chosen per line:

   | rate name  | rate |
   |------------|------|
   | `standard` | 0.20 |
   | `reduced`  | 0.05 |
   | `zero`     | 0    |

   Any other rate name is a programming error: `Invoice.add` raises `ValueError` immediately.
4. Lines are never rounded. The invoice sums the unrounded line nets and the unrounded line VAT amounts, then rounds each sum once to 2 decimal places using commercial rounding (round half up: 0.125 becomes 0.13, 0.025 becomes 0.03).
5. `gross` is the rounded net plus the rounded VAT, so the three printed figures always add up.
