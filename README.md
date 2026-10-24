<<<<<<< HEAD
# Retail & E-commerce Data Cleaning and Transformation Pipeline

A repeatable, auditable pandas pipeline that cleans raw retail order data, quarantines records it cannot safely resolve, links returns, payments and shipments to order lines, tests itself against the brief's test cases, reports data quality, and produces analytical outputs. Built for the *Retail & E-commerce Data Cleaning and Transformation Use Case* (20 cleaning scenarios, 15-16 transformations, TC01-TC10).

The pipeline addresses the limitations listed below and was verified on two real datasets (Olist and UCI Online Retail II, 1.07M rows). See `docs/REAL_DATA_RESULTS.md` for the evidence and section 2 for what changed.

## 1. Repository layout

```
retail-pipeline/
├── src/retail_pipeline/        # the library (one module per concern, see docs/MODULE_GUIDE.md)
│   ├── config.py  flags.py  utils.py  reference.py  fx.py
│   ├── identifiers.py  money.py  timestamps.py  labels.py  promotions.py  privacy.py
│   ├── cleaning.py             # clean_row(): every rule applied to one raw record
│   ├── pipeline.py             # run_pipeline(): clean -> de-duplicate -> classify
│   ├── returns.py  payments.py  shipments.py  events.py  anomalies.py
│   ├── transforms.py           # analytical outputs (net sales, AOV, cohorts, CLV, ...)
│   ├── quality.py              # dq_report()
│   ├── demo_data.py            # the brief's sample rows + load_orders()
│   └── adapters.py             # Olist / Online Retail II -> raw schema (assumptions in docstrings)
├── tests/                      # 49 tests (TC01-TC10, B01-B16, R/D/M/K/S/G/PR/P/SH/E/A/T groups), split by topic
├── scripts/                    # generate_dummy_data.py, run_real_data_test.py
├── notebooks/                  # walk-through notebook (runs the package; ships executed)
├── examples/sample_output/     # CSVs produced by the notebook on the demo data
├── docs/                       # MODULE_GUIDE.md, REAL_DATA_RESULTS.md
├── pyproject.toml  requirements*.txt  .github/workflows/tests.yml
```

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt 
pip install -e ".[dev]"             # add `tzdata` on Windows; pycountry is only for the Online Retail II adapter
pytest                              # 49 passed
export PII_TOKEN_KEY="a-long-random-secret"         # required for the privacy-safe extract
python scripts/run_real_data_test.py --olist data/olist --retail2 data/online_retail_II.csv
python scripts/generate_dummy_data.py --orders 500 --seed 42 --out data     # messy synthetic input
jupyter notebook notebooks/Retail_Ecommerce_Data_Cleaning_Pipeline.ipynb
```

```python
import retail_pipeline as rp
res = rp.run_pipeline(rp.ALL_RAW)     # or your own DataFrame + ref=RefData(...)
```

`docs/REAL_DATA_RESULTS.md` holds the real-data verification run. `scripts/run_real_data_test.py` uses the Unix-only `resource` module for peak-memory reporting.

## 2. Known limitations and how they are handled

| Limitation | Handling | Tests |
|---|---|---|
| Reference tables and FX rates were placeholders | `RefData` object holds catalogue, customer master, vocabularies, currencies, ID rules, source zone, promotions. `RefData.from_csv`, `derive_reference` (labelled *derived*), `load_fx_rates` (validates dates, positivity, duplicates), `fx_coverage` (lists missing date/currency pairs). Integrity of supplier/category keys is checked when a `RefData` is built | R01-R03 |
| `dd-mm-yyyy` always quarantined; fixed UTC offsets only | `source_tz="Europe/London"` (IANA, DST-aware); wall times in a DST gap or fold are quarantined, never guessed. `date_order="DMY"/"MDY"` declared by the source, or `"infer"` from one-sided evidence in the column (refuses to infer from ambiguous-only or conflicting data). Flexible formats (`5/14/2026 9:05`, `14.05.2026`). A declared order that the data contradicts is `TS_INVALID` | D01-D04 |
| Money was float64 | Integer minor units end to end (`Gross_Minor`, `Net_Minor`, `Net_Reporting_Minor`, `Refund_Minor` ...); FX applied with `Decimal`, half-up to minor units; DQ reconciliation compares exact integers. Float columns remain as display copies. Rounding of >2 decimal prices is flagged (`PRICE_ROUNDED`) | M01-M03 |
| Token key defaulted to a development key | Fail closed: `MissingTokenKeyError` unless `PII_TOKEN_KEY` (16+ chars) or `key=` is given; random per-run key only by explicit opt-in (`PII_ALLOW_EPHEMERAL_KEY=1`, warns that tokens will not join across runs). Tokenisation moved out of the cleaning step | K01 |
| Small synthetic data only | Tested on 1,067,371 real rows. 2.6x faster than the original row-by-row implementation on identical input (measured); `chunks=N` partitions by order ID, `audit="capped"` bounds memory, `slim=True` drops raw copies. Peak 2.2 GB for 1.05M rows | S00 + real-data run |
| Scenarios 10, 12, 14 "not in sample" | `clean_payments` + `reconcile_payments`, promotion evaluation in `clean_row` (applied / expired / rejected / unknown / unverifiable), `clean_shipments` (carrier, tracking, status, chronology) | P01-P03, PR01, SH01 |
| Scenario 16 partial, scenario 20 partial | `robust_anomalies` (trailing median/MAD; `NO_BASELINE` when history is short), `order_spikes`, `refund_ratio_flags`, repeated failed payments, `reconcile_events` (lifecycle order beats arrival order; late arrivals and contradictions flagged) | A01, A02, E01 |
| State and postal code "extend the maps" | `normalize_state` (US/IN/BR), `normalize_postal` (IN/US/BR/GB); no zero-padding guesses | G01 |
| Transformations #3, 4, 8, 10, 11, 12 missing | `cohort_analysis`, `funnel`, `fulfilment_performance`, `payment_rates`, `clv_historical` (descriptive), `regional_summary`, `promotion_summary` | T01, P03, SH01 |
| `display` NameError outside Jupyter | Shim added | - |
| Returns checked per row only | Cumulative quantity and refund checks (a second return cannot exceed what is left) | B14 |

Also new: non-product lines (postage, fees, adjustments) are kept out of product sales; `discount_policy="ABSENT_IN_SOURCE"` is an explicit, declared policy for sources with no discount field (net = gross, reported in the DQ report), while a blank discount in a source that has the field still stays NULL.

## 3. Design principles (unchanged)

1. **Never guess.** Ambiguous or impossible values are flagged and quarantined. A blank discount is never turned into 0. An unknown customer ID is never replaced. Time zones and date orders are used only when the source *declares* them (and the use is recorded in `TS_Status`).
2. **Everything is traceable.** `Raw_Row_ID` on every record; audit log (raw, clean, rule); exceptions table with severity.
3. **Nulls stay null** unless a documented rule says otherwise.
4. **Reproducible.** Same input, same output (`B15`); chunked and single runs are identical (`S00`).

## 4. Pipeline

```
raw DataFrame -> clean_row() per row (memoised parsers) -> cleaned record + flags + audit
              -> de-duplication on Line_Key = Order_ID | Line_ID | SKU
                    authoritative = highest Event_Version -> clean timestamp -> most complete -> earliest
                    same-version rows that disagree -> CONFLICTING_DUPLICATE (nothing silently dropped)
              -> Disposition: CLEAN | REVIEW | SUPERSEDED_DUPLICATE
              -> PipelineResult: standardized, clean, review, superseded, fulfilled, exceptions, audit
related tables: clean_returns / clean_payments / clean_shipments link to the authoritative order lines
```

```python
res = run_pipeline(raw, ref=my_ref, fx_rates=load_fx_rates("fx.csv"), date_order="infer", chunks=8, audit="capped", slim=True)
returns, rex = clean_returns(returns_raw, res.standardized, my_ref)
pays, pex   = clean_payments(pay_raw, res.standardized, my_ref); recon = reconcile_payments(pays, res.standardized, ("Net_Minor", "Shipping_Minor"))
ship, sex   = clean_shipments(ship_raw, res.standardized, my_ref)
dq = dq_report(raw, res, returns, rex, my_ref, recon)
```

## 5. Business rules (changes in bold)

| # | Rule |
|---|---|
| A1 | Order IDs follow the source's configured rule (`order_id_rule(regex, case)`); default `ORD-<digits>`. Invalid -> `INVALID_ORDER_ID` |
| A2 | Customer IDs resolve through the customer master; unmatched stay NULL and go to the exception queue |
| A3 | An explicit offset or `Z` wins. **Otherwise the timestamp is quarantined unless the source declares `source_tz` (preferred) or a fixed offset. DST gap/fold wall times are quarantined. dd/mm vs mm/dd is resolved only if one reading is calendar-valid, the source declares it, or `infer_date_order` finds one-sided evidence** |
| A4 | Catalogue name always wins; SKU matching on an alphanumeric key; name fallback is warned |
| A5 | **Amounts are exact integer minor units computed from sold-unit values; per-unit float columns are display only** |
| A6 | A percentage discount is a percentage of the unit price, stored absolute; a blank discount stays NULL |
| A7 | Currency symbols stripped; unambiguous symbols may be inferred (warned); `$` is never assumed USD |
| A8 | FX uses only a supplied rate keyed by the order's UTC date; no rate -> native amount kept, `FX_UNAVAILABLE`; **`fx_coverage` lists gaps** |
| A9-A10 | Status vocabulary and revenue classes are configurable per source; `Return` on an order line -> review |
| A11 | Duplicate key `Order_ID + Line_ID + SKU` |
| A12 | Ranges: quantity 1..`qty_max`, price > 0 and <= `price_max`, 0 <= discount <= price (all `RefData` parameters) |
| A13 | Raw email/phone never enter the dataset; **tokens require a secret** |
| A14 | Blocking flags -> review queue and excluded from metrics; warnings stay usable but are listed |

## 6. Flags

**Blocking:** `INVALID_ORDER_ID`, `TS_AMBIGUOUS_NO_TZ`, `TS_AMBIGUOUS_DATE_ORDER`, `TS_INVALID`, `TS_MISSING`, `TS_DST_AMBIGUOUS`, `TS_DST_NONEXISTENT`, `INVALID_QTY`, `QTY_OUT_OF_RANGE`, `UNIT_UNKNOWN`, `INVALID_PRICE`, `PRICE_OUT_OF_RANGE`, `DISCOUNT_INVALID`, `SKU_UNKNOWN`, `CURRENCY_UNKNOWN`, `CURRENCY_SYMBOL_CONFLICT`, `STATUS_UNKNOWN`, `RETURN_ON_ORDER_LINE`, `CONFLICTING_DUPLICATE`.
**Warning:** `DISCOUNT_UNKNOWN`, `FX_UNAVAILABLE`, `SKU_RESOLVED_VIA_NAME`, `CURRENCY_INFERRED_FROM_SYMBOL`, `CUSTOMER_ID_MISSING`, `CUSTOMER_UNMATCHED`, `CHANNEL_UNMAPPED`, `COUNTRY_UNMAPPED`, `TS_TZ_ASSUMED`, `TS_DATE_ORDER_ASSUMED`, `PRICE_ROUNDED`, `SHIPPING_INVALID`, `TAX_INVALID`, `STATE_UNMAPPED`, `POSTAL_INVALID`, `PROMO_UNKNOWN_CODE`, `PROMO_EXPIRED`, `PROMO_REJECTED`, `PROMO_UNVERIFIABLE`, `PROMO_NO_DISCOUNT`.
**Returns:** `RETURN_UNMATCHED_LINE`, `RETURN_QTY_EXCEEDS_SOLD`, `REFUND_EXCEEDS_LINE`, `RETURN_CURRENCY_MISMATCH`, `RETURN_REFUND_INVALID` (blocking); `RETURN_REASON_UNMAPPED`, `RETURN_DUPLICATE_ID` (warning).
**Payments / shipments / events:** `PAYMENT_UNMATCHED_ORDER`, `PAYMENT_AMOUNT_INVALID`, `PAYMENT_CURRENCY_MISMATCH` (blocking); `PAYMENT_METHOD_UNMAPPED`, `PAYMENT_STATUS_UNKNOWN`, `PAYMENT_ZERO_AMOUNT`, `REPEATED_FAILED_PAYMENTS`; `SHIPMENT_UNMATCHED_ORDER`, `SHIPMENT_TS_NOT_USABLE`, `DELIVERED_BEFORE_SHIPPED`, `SHIPPED_BEFORE_ORDERED` (exclude from lead-time metrics); `CARRIER_UNMAPPED`, `TRACKING_INVALID`, `SHIP_STATUS_UNKNOWN`, `DELIVERED_WITHOUT_TIMESTAMP`, `STATUS_TS_MISMATCH`; `EVENT_BEFORE_PREDECESSOR`, `LATE_ARRIVING`, `ARRIVED_OUT_OF_ORDER`, `DUPLICATE_EVENT_TYPE`.

## 7. Tests (49)

TC01-TC10 from the brief; B01-B16 boundary and duplicate cases (adapted to minor units); and one group per fix: R01-R03 reference data, D01-D04 dates and zones, M01-M03 exact money, K01 token key, S00-S01 scale and declared policies, G01 geography, PR01 promotions, P01-P03 payments, SH01 shipments, E01 events, A01-A02 anomalies, T01 cohorts / funnel / CLV. Each test records scenario, input, expected, actual, status and exception output (`test_results.csv`).

## 8. Metric definitions

All sums use integer minor units; currencies are never mixed; only authoritative CLEAN FULFILLED lines count.

| Metric | Definition |
|---|---|
| Gross / Discounts / Net | sum of qty x price / qty x discount / gross - discounts |
| AOV | net / distinct orders, over orders whose every line has a known net |
| Return rate | linked returned units / fulfilled units sold |
| Cohort, repeat rate | cohort = UTC month of first fulfilled order; repeat = customers with >= 2 distinct orders / customers |
| Lead time, on-time | ship->delivery days; delivered <= promised, on rows with usable, chronologically valid timestamps only |
| Payment rates | over attempts with a recorded final-ish status; PENDING / NOT_RECORDED excluded from denominators |
| Historical CLV | realised fulfilled net per customer to date (descriptive, not predictive) |
| Funnel | distinct units reaching each stage; `strict` requires all earlier stages |

## 9. Remaining limitations (by design or by data)

* `demo_reference()` is still illustrative; real runs must supply a `RefData`. A *derived* reference (Online Retail II) cannot detect unknown SKUs or customers, and the DQ report says so.
* Declared assumptions (source zone, currency, discount policy) are the caller's responsibility; the pipeline records and reports them but cannot verify them.
* Currencies with other than 2 decimals (JPY, KWD) are unsupported.
* Credit notes with no reference to the original invoice can never be linked (Online Retail II); they are reported as unmatched, not guessed.
* Exact repeated rows without a source line id are reported (`Possible duplicate lines`), not dropped.
* Incremental promotion sales and predictive CLV need holdouts or models beyond cleaning. Inventory sell-through and device/acquisition comparisons need data none of the tested datasets carry.
* Tracking-ID patterns and state/postal tables are configurable defaults; verify against current standards.

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| `MissingTokenKeyError` | `export PII_TOKEN_KEY=...` (16+ chars) |
| Everything in review with `TS_AMBIGUOUS_NO_TZ` | Source has no zone: declare `source_tz` in `RefData` (only if you know it) |
| A few rows `TS_DST_AMBIGUOUS` / `TS_DST_NONEXISTENT` | Expected: local times in the DST fold/gap cannot be mapped to one instant |
| `ZoneInfoNotFoundError` on Windows | `pip install tzdata` |
| Memory pressure on 1M+ rows | `chunks=8, audit="capped", slim=True` |
| USD/BRL rows have empty `Net_Reporting_Minor` | No FX rate for that date (intentional); pass `fx_rates` |
=======
# Retail-E-commerce-Data-Cleaning-and-Transformation-Use-Case-
>>>>>>> c5d4765195d8a1b467fc22f223995a78217574e4
