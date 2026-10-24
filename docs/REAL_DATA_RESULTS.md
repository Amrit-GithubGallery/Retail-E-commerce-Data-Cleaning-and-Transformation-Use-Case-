# Real-data verification run

**Provenance (read this first).** The sandbox that produced these numbers could not reach kaggle.com, so the files came from public third-party GitHub copies of the datasets. Their row counts match the published figures (Olist 99,441 orders / 103,886 payments; Online Retail II 1,067,371 rows, as stated on the UCI page), but they are not downloads from Kaggle itself. Re-run on your own Kaggle download with `python scripts/run_real_data_test.py --olist DIR --retail2 FILE`; the numbers should be identical if the files are.

Both adapters declare their assumptions (see `src/retail_pipeline/adapters.py`): currency, source time zone, no-discount policy, derived masters. These are the caller's declarations, not facts the pipeline verified.

## Online Retail II (UCI 502; Kaggle mirror `mashlyn/online-retail-ii-uci`; CC BY 4.0 per the UCI page)

| Measure | Result |
|---|---|
| Rows | 1,067,371 = 1,047,877 sales lines + 19,494 credit-note lines |
| Runtime / memory | 88 s for the sales lines (about 11,900 rows/s), 2.2 GB peak, 8 chunks |
| Disposition | 1,041,645 clean, 6,232 quarantined, 0 superseded |
| Blocking flags | `INVALID_PRICE` 6,225 (zero or negative prices, incl. bad-debt adjustments) · `INVALID_QTY` 3,457 · `QTY_OUT_OF_RANGE` 9 (> 10,000 units) |
| Warnings | `CUSTOMER_ID_MISSING` 242,257 (23.1%, kept NULL, never replaced) · `COUNTRY_UNMAPPED` 2,435 ("Unspecified", "European Community", ...) |
| Timestamps | all 1,047,877 resolved under the declared zone Europe/London (DST-aware), recorded as `OK_ASSUMED_TZ` |
| Credit notes | 0 of 19,494 linkable: the data has no reference to the original invoice. Reported as unmatched, not guessed |
| Possible duplicate lines | 66,472 rows identical on order/SKU/time/qty/price; reported, **not dropped** (no source line id) |
| DQ report | 21 PASS, 7 WARN, 0 FAIL |
| Outputs | net sales GBP 19,859,254.37 on 1,037,074 fulfilled lines; AOV GBP 502.59 over 39,514 orders; 72.3% of identified customers repeat; 20 anomalous days of 739 against a trailing baseline |

## Olist Brazilian E-Commerce (Kaggle `olistbr/brazilian-ecommerce`)

| Measure | Result |
|---|---|
| Lines / orders | 112,650 order-item lines on 98,666 orders (99,441 orders in total; 775 have no items) |
| Runtime | 12.8 s for the pipeline, about 0.5 GB when run alone |
| Disposition | 112,632 clean, 18 quarantined |
| Why 18 | all are `TS_DST_AMBIGUOUS`: local purchase times that fall in the repeated hour when São Paulo clocks went back; the pipeline refuses to pick one instant |
| Revenue classes | 110,197 fulfilled lines, 1,904 in pipeline, 549 excluded (canceled / unavailable) |
| Payments | 103,886 payments, methods CARD 78,324 · BANK_SLIP (boleto) 19,784 · VOUCHER 5,775 · 3 `not_defined` left unmapped; 830 payments belong to orders with no items; 9 zero-value |
| Payment reconciliation | payments equal items + freight exactly (centavos) for 98,077 of 98,654 orders (99.42%); 367 paid more, 210 paid less |
| Shipments | 99,441 orders; 98,477 eligible for lead-time metrics; excluded: 775 unmatched, 166 carrier date before purchase, 23 delivered before carrier handover, 8 delivered without timestamp |
| Fulfilment | 91.9% on time against the promised date (96,288 orders judged); mean ship-to-delivery 9.3 days. No carrier column exists in the data, so there is no per-carrier split |
| Events | 5,519 events time-stamped before an earlier lifecycle stage, across 1,382 orders |
| Customers | 3.0% repeat rate over 93,346 customers (by `customer_unique_id`) |
| Not computable | payment authorisation/failure rates (no payment status in the source); promotions (no promo field) |
| DQ report | 21 PASS, 5 WARN, 0 FAIL |
| Outputs | net sales BRL 13,220,126.62 (net = gross because the source records no discounts, a declared policy) |

## What these runs do and do not show

They show the cleaning logic, reconciliation checks and scale behaviour hold up on real, messy data and surface real quirks (DST folds, credit notes without invoice references, orders without items, impossible event chronology). They do **not** validate the declared assumptions (for example that Olist timestamps are local São Paulo time), and the metrics are only as meaningful as those declarations.