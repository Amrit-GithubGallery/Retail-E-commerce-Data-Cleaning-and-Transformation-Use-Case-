"""Run every registered case and return the results table (also exported to test_results.csv by the notebook / scripts)."""
import importlib

import pandas as pd

for _m in ("test_analytics", "test_boundaries", "test_brief_cases", "test_events_anomalies", "test_geography_promotions", "test_money",
           "test_payments_shipments", "test_privacy", "test_reference_data", "test_scale", "test_timestamps"):
    importlib.import_module(f".{_m}", __package__)   # importing registers the cases
from .helpers import TEST_LOG, _TESTS, run_test


def run_all_tests():
    """Execute every registered test; returns the results table (also kept in TEST_LOG)."""
    TEST_LOG.clear()
    for t in _TESTS: run_test(*t)
    return pd.DataFrame(TEST_LOG).sort_values("Test ID").reset_index(drop=True)
