# Module guide

The pipeline started as one notebook (cells 0-28 held the definitions, 29-52 ran them). It is now an installable package; this table maps each old definition cell to the module that holds it. Code was moved verbatim; only imports were made explicit.

| Module | Old notebook cell | Contents |
|---|---|---|
| `src/retail_pipeline/config.py` | 2 | `OUTPUT_DIR`, `CENT`. (The notebook-only `display` shim and pandas display options moved into the notebook setup cell.) |
| `src/retail_pipeline/flags.py` | 4 | `BLOCKING_FLAGS`, `WARNING_FLAGS`, `severity()`. Move a code between the sets to make a rule stricter or looser. |
| `src/retail_pipeline/utils.py` | 6 | `_blank`, `_key`, `_norm_label` helpers shared by many modules. |
| `src/retail_pipeline/reference.py` | 6 | Default vocabularies, `RefData`, `demo_reference()`, `DEFAULT_REF`, `set_default_reference`, `derive_reference`, ID-rule builders. |
| `src/retail_pipeline/fx.py` | 6 | `load_fx_rates`, `fx_coverage`. |
| `src/retail_pipeline/identifiers.py` | 8 | `normalize_order_id`, `resolve_customer`, `resolve_sku`, `normalize_qty`. |
| `src/retail_pipeline/money.py` | 8 | `parse_money(_ex)`, `to_minor`, `minor_to_decimal`, `parse_discount`, `normalize_currency`. |
| `src/retail_pipeline/timestamps.py` | 10 | `parse_timestamp`, `fmt_utc`, `infer_date_order`. |
| `src/retail_pipeline/labels.py` | 12 | `normalize_status`, `normalize_label`, `normalize_state`, `normalize_postal`. |
| `src/retail_pipeline/promotions.py` | 12 | `normalize_promo_code`, `evaluate_promo`. |
| `src/retail_pipeline/privacy.py` | 12 | `mask_email`, `mask_phone`, `resolve_token_key`, `tokenize`, `analyst_extract`, `MissingTokenKeyError`. |
| `src/retail_pipeline/cleaning.py` | 14 | `clean_row()`. |
| `src/retail_pipeline/pipeline.py` | 16 | `run_pipeline()`, `PipelineResult`. |
| `src/retail_pipeline/returns.py` | 18 | `clean_returns`. |
| `src/retail_pipeline/payments.py` | 18 | `clean_payments`, `reconcile_payments`. |
| `src/retail_pipeline/shipments.py` | 18 | `clean_shipments`. |
| `src/retail_pipeline/events.py` | 20 | `reconcile_events`. |
| `src/retail_pipeline/anomalies.py` | 20 | `robust_anomalies`, `daily_metric_anomalies`, `order_spikes`, `refund_ratio_flags`. |
| `src/retail_pipeline/transforms.py` | 22 | `daily_net_sales`, `product_ranking`, `aov_table`, `return_rates`, `cohort_analysis`, `regional_summary`, `fulfilment_performance`, `payment_rates`, `funnel`, `clv_historical`, `promotion_summary`. |
| `src/retail_pipeline/quality.py` | 24 | `dq_report`. |
| `src/retail_pipeline/demo_data.py` | 26 | `SAMPLE_RAW`, `EXTENDED_RAW`, `DEMO_RETURNS_RAW`, `ALL_RAW`, `load_orders`. |
| `src/retail_pipeline/adapters.py` | - (was `real_data_adapters.py`) | `olist_frames`, `online_retail_frames`: map real datasets onto the raw schema; assumptions declared in docstrings |

Dependency order (no cycles): `config, flags, utils` -> `reference` -> `fx, identifiers, money, timestamps, labels, promotions, privacy` -> `cleaning` -> `pipeline` -> `returns, payments, shipments` -> `events, anomalies, transforms, quality, demo_data`.

The package root re-exports the public API (`import retail_pipeline as rp; rp.run_pipeline(...)`). `DEFAULT_REF` is deliberately not re-exported, because `set_default_reference()` rebinds it; read it as `retail_pipeline.reference.DEFAULT_REF`.

## Tests

Each old `@case(...)` test is now a `test_*` function (same ID, scenario, input and expectation in the decorator). `pytest` runs them directly; `tests/report.py::run_all_tests()` returns the same results table the notebook exports as `test_results.csv`.

| File | Test IDs |
|---|---|
| `tests/test_brief_cases.py` | TC01-TC10 |
| `tests/test_boundaries.py` | B01-B16 |
| `tests/test_reference_data.py` | R01-R03 |
| `tests/test_timestamps.py` | D01-D04 |
| `tests/test_money.py` | M01-M03 |
| `tests/test_privacy.py` | K01 |
| `tests/test_scale.py` | S00-S01 |
| `tests/test_geography_promotions.py` | G01, PR01 |
| `tests/test_payments_shipments.py` | P01-P03, SH01 |
| `tests/test_events_anomalies.py` | E01, A01-A02 |
| `tests/test_analytics.py` | T01 |

Shared fixtures (`mk`, `P`, `flags_of`, `env`, `sample_res`, `expected_view`) are in `tests/helpers.py`.

## Which module to edit

| I want to... | Go to |
|---|---|
| Make a flag stricter or looser | `flags.py` |
| Use my own catalogue, customers, currencies, time zone, ID format | `reference.py` (`RefData`), then pass `ref=` to `run_pipeline` |
| Add a status, channel, country or return-reason label | `reference.py` (vocabulary dicts) |
| Change plausible quantity or price ceilings | `RefData(qty_max=..., price_max=...)` |
| Add a currency symbol | `money.py` (`_SYM2CCY`, `_MONEY_RE`) |
| Change timestamp handling | `timestamps.py` |
| Add states or postal formats | `labels.py` (`_STATES`, `_POSTAL`) |
| Change how duplicates are chosen | `pipeline.py` |
| Add a metric | `transforms.py` |
| Add a data-quality check | `quality.py` |
| Add a test | any `tests/test_*.py` (decorate with `@case(...)`, name it `test_<id>`) |
| Point at your own raw file | `demo_data.load_orders(path)` |
| Run on a real dataset | `scripts/run_real_data_test.py` |
