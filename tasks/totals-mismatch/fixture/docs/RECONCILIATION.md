# Settlement reconciliation

The nightly job turns a log of payment events into one **payout** per merchant and settlement day. Finance compares each payout's net amount with the bank statement. This page is the contract: the numbers the bank pays are the numbers these rules produce, and a payout that disagrees with the statement is wrong in the pipeline, not in the statement.

## Inputs

`data/` holds four files (the job and `tools/reconcile.py` take the directory as an argument):

- `events.jsonl`: one JSON object per line: `event_id`, `merchant_id`, `type` (`charge`, `refund` or `refund_reversal`), `status`, `currency` (ISO code), `amount_minor` (a positive integer in the minor units of `currency`), `occurred_at` and `received_at` (UTC, ISO 8601 with a trailing `Z`).
- `merchants.json`: per merchant `timezone` (an IANA zone name), `settlement_currency`, `fee_bps` (percentage fee in basis points) and `fixed_fee_minor` (a fixed fee per charge, in minor units of the settlement currency).
- `rates.csv`: `day,from,to,rate`. `rate` is how many major units of `to` one major unit of `from` buys on that settlement day.
- `bank_statement.csv`: `merchant_id,day,currency,net_minor`, the amount the bank paid out.

## 1. What counts as one event

Events with a `status` other than `succeeded` are ignored before anything else.

Event ids are issued by one ledger per merchant and currency, so an id is only unique within its merchant and currency. **One event is identified by the triple (`merchant_id`, `currency`, `event_id`).** The PSP resends events after timeouts, so the same triple can appear several times with identical content: count it once, keeping the first occurrence in file order. Two records that differ in any part of the triple are two different events, even if their amounts and times are equal.

## 2. Settlement day

A payout covers one calendar day on the wall clock of the merchant's `timezone`. The settlement day of an event is the local date of its `occurred_at` in that zone, using the zone's rules as they were at that instant, including daylight saving time. `received_at` plays no part. A local day can be 23 or 25 hours long when the clocks change, and zones do not all use whole-hour offsets or the same transition dates (the southern hemisphere changes in the opposite season). The `day` in the rates table and in the statement is this settlement day.

## 3. Currencies, minor units and conversion

`amount_minor` counts the smallest unit of its currency. The number of decimal places in the major unit depends on the currency:

| decimal places | currencies |
|---|---|
| 0 | `JPY`, `KRW`, `CLP`, `VND` |
| 3 | `KWD`, `BHD`, `JOD` |
| 2 | every other currency |

So 1500 `JPY` is 1500 yen, 1500 `USD` is 15.00 dollars and 1500 `KWD` is 1.500 dinars.

Every event is converted into the merchant's settlement currency on its own, using the rate for the event's settlement day and the pair (event currency, settlement currency): `amount in settlement major units = amount in event major units * rate`. The result is rounded once, to a whole number of minor units of the settlement currency (rule 6). An event already in the settlement currency is not converted and not rounded. A missing rate is an error (`ValueError`); never guess one.

Example: 1500 `USD` to `EUR` at 0.9234 is 15.00 * 0.9234 = 13.851 euro, which is 1385 minor units. 1000 `JPY` to `EUR` at 0.0061 is 6.1 euro, which is 610 minor units. 12 `EUR` (1200 minor) to `JPY` at 162.35 is 1948.2 yen, which is 1948.

## 4. Refunds and how they net

All amounts below are in the settlement currency after conversion, within one settlement day (a refund belongs to the day on which it occurred, not to the day of the charge it refunds).

- `charges` = the sum of `charge` events.
- `refunds` = the sum of `refund` events minus the sum of `refund_reversal` events (a reversal is a refund the card network bounced; it gives the money back to the merchant and may exceed the day's refunds, making `refunds` negative).
- The balance before the fee is `charges - refunds`. It can be negative on a day with more refunds than charges. Such a day still gets a payout row, with a negative net.

## 5. Fees

The fee of a payout has two parts.

- A percentage part: `fee_bps / 10000` of the balance before the fee (`charges - refunds`), computed **once for the whole payout** and rounded once. If the balance is zero or negative, the percentage part is 0 (no fee is credited back).
- A fixed part: `fixed_fee_minor` for every `charge` event in the payout. Refunds and reversals neither add nor remove fixed fees.

`net = charges - refunds - fee`. A payout exists for every (merchant, settlement day) that has at least one counted event.

## 6. Rounding

Whenever a value is rounded to minor units, it is rounded half to even (banker's rounding): a value exactly halfway between two whole units goes to the even one (2.5 becomes 2, 3.5 becomes 4, -2.5 becomes -2). Exactly two things are ever rounded: the conversion of one event (rule 3) and the percentage fee of one payout (rule 5). Everything else is integer addition and subtraction. Rounding is to the minor unit of the currency the value ends up in, so the percentage fee of a `JPY` merchant is a whole number of yen.

Example: a `USD` merchant at 290 bps with three charges of 1500 (minor units) and no refunds has a balance of 4500 and a percentage fee of 4500 * 0.029 = 130.5, which is 130 (the even neighbour). Rounding each charge's fee on its own (43.5 becomes 44, three times, 132) is wrong; the rule is one rounding per payout.

## 7. Entry points and the statement

- `settle.pipeline.run(data_dir)` returns the payouts sorted by merchant id and day. Each has `merchant_id`, `day` (`YYYY-MM-DD`), `currency` (the settlement currency), `charges_minor`, `refunds_minor`, `fee_minor` and `net_minor`.
- `python tools/reconcile.py [--data DIR]` compares the payouts with `bank_statement.csv` and prints, per merchant, the days that differ. Its exit status is 0 only when every merchant-day matches. It shows symptoms; it does not say why.

The statement in `data/` is correct and the pipeline must match it. The same rules must hold for every other dataset in this format (other merchants, other zones, other currencies, other days), not just the one in `data/`.
