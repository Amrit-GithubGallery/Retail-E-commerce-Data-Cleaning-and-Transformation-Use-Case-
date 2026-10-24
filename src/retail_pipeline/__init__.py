"""Retail & e-commerce data cleaning and transformation pipeline.

Public API re-exported from the sub-modules. See docs/MODULE_GUIDE.md for what lives where.
"""
from .config import CENT, OUTPUT_DIR
from .flags import BLOCKING_FLAGS, WARNING_FLAGS, severity
from .reference import CHANNEL_MAP, COUNTRY_MAP, REASON_MAP, REVENUE_CLASS, RefData, STATUS_MAP, UNIT_FACTORS, demo_reference, derive_reference, numeric_customer_normalizer, order_id_rule, set_default_reference
from .fx import fx_coverage, load_fx_rates
from .identifiers import normalize_order_id, normalize_qty, resolve_customer, resolve_sku
from .money import minor_to_decimal, normalize_currency, parse_discount, parse_money, parse_money_ex, to_minor
from .timestamps import fmt_utc, infer_date_order, parse_timestamp
from .labels import normalize_label, normalize_postal, normalize_state, normalize_status
from .promotions import evaluate_promo, normalize_promo_code
from .privacy import MissingTokenKeyError, analyst_extract, mask_email, mask_phone, resolve_token_key, tokenize
from .cleaning import clean_row
from .pipeline import ASSUMPTION_FLAGS, PipelineResult, run_pipeline
from .returns import clean_returns
from .payments import PAYMENT_METHOD_MAP, PAYMENT_STATUS_MAP, clean_payments, reconcile_payments
from .shipments import CARRIER_MAP, SHIP_STATUS_MAP, TRACKING_RULES, clean_shipments
from .events import LIFECYCLE, reconcile_events
from .anomalies import daily_metric_anomalies, order_spikes, refund_ratio_flags, robust_anomalies
from .transforms import aov_table, clv_historical, cohort_analysis, daily_net_sales, fulfilment_performance, funnel, payment_rates, product_ranking, promotion_summary, regional_summary, return_rates
from .quality import dq_report
from .demo_data import ALL_RAW, DEMO_RETURNS_RAW, EXTENDED_RAW, EXT_COLS, RAW_COLS, SAMPLE_RAW, load_orders
from .utils import _blank   # used by the real-data adapters

__version__ = "1.0.0"

__all__ = [
    "ALL_RAW",
    "ASSUMPTION_FLAGS",
    "BLOCKING_FLAGS",
    "CARRIER_MAP",
    "CENT",
    "CHANNEL_MAP",
    "COUNTRY_MAP",
    "DEMO_RETURNS_RAW",
    "EXTENDED_RAW",
    "EXT_COLS",
    "LIFECYCLE",
    "MissingTokenKeyError",
    "OUTPUT_DIR",
    "PAYMENT_METHOD_MAP",
    "PAYMENT_STATUS_MAP",
    "PipelineResult",
    "RAW_COLS",
    "REASON_MAP",
    "REVENUE_CLASS",
    "RefData",
    "SAMPLE_RAW",
    "SHIP_STATUS_MAP",
    "STATUS_MAP",
    "TRACKING_RULES",
    "UNIT_FACTORS",
    "WARNING_FLAGS",
    "analyst_extract",
    "aov_table",
    "clean_payments",
    "clean_returns",
    "clean_row",
    "clean_shipments",
    "clv_historical",
    "cohort_analysis",
    "daily_metric_anomalies",
    "daily_net_sales",
    "demo_reference",
    "derive_reference",
    "dq_report",
    "evaluate_promo",
    "fmt_utc",
    "fulfilment_performance",
    "funnel",
    "fx_coverage",
    "infer_date_order",
    "load_fx_rates",
    "load_orders",
    "mask_email",
    "mask_phone",
    "minor_to_decimal",
    "normalize_currency",
    "normalize_label",
    "normalize_order_id",
    "normalize_postal",
    "normalize_promo_code",
    "normalize_qty",
    "normalize_state",
    "normalize_status",
    "numeric_customer_normalizer",
    "order_id_rule",
    "order_spikes",
    "parse_discount",
    "parse_money",
    "parse_money_ex",
    "parse_timestamp",
    "payment_rates",
    "product_ranking",
    "promotion_summary",
    "reconcile_events",
    "reconcile_payments",
    "refund_ratio_flags",
    "regional_summary",
    "resolve_customer",
    "resolve_sku",
    "resolve_token_key",
    "return_rates",
    "robust_anomalies",
    "run_pipeline",
    "set_default_reference",
    "severity",
    "to_minor",
    "tokenize",
]
