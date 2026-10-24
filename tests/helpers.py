"""Shared test helpers and the test-case registry (used for the test_results.csv report)."""
import contextlib
import functools
import numpy as np
import os
import pandas as pd
from src.retail_pipeline import SAMPLE_RAW, run_pipeline


TEST_LOG, _TESTS = [], []

TEST_KEY = "unit-test-secret-key-0123456789"

def run_test(tid, scenario, input_desc, expected, fn):
    try: actual = fn(); status, exc = "PASS", ""
    except AssertionError as e: actual, status, exc = "assertion failed", "FAIL", str(e) or "assertion failed"
    except Exception as e: actual, status, exc = "error", "ERROR", repr(e)
    TEST_LOG.append({"Test ID": tid, "Scenario": scenario, "Input / Condition": input_desc, "Expected Result": expected,
                     "Actual Result": actual, "Status": status, "Exception Output": exc})

def case(tid, scenario, input_desc, expected):
    """Register a test for the results table and expose it to pytest (return values are for the table, not pytest)."""
    def deco(fn):
        _TESTS.append((tid, scenario, input_desc, expected, fn))
        @functools.wraps(fn)
        def wrapper(): fn()
        return wrapper
    return deco

def mk(**over):
    """One raw row; keyword names map underscores to spaces (Unit_Price -> 'Unit Price')."""
    base = {"Order ID": "ORD-9001", "Customer ID": "CUST-007", "Order TS": "2026-05-14T14:30:00Z", "SKU": "MUG-BLK",
            "Product": "Black Ceramic Mug", "Qty": 1, "Unit Price": "450.00", "Discount": "0", "Currency": "INR", "Status": "Delivered"}
    base.update({k.replace("_", " "): v for k, v in over.items()}); return base

def P(*rows, **kw): return run_pipeline(pd.DataFrame(list(rows)), **kw)

def flags_of(res_, i=0): return {c for c, _ in res_.standardized.iloc[i].Flags}

@contextlib.contextmanager
def env(**kv):
    old = {k: os.environ.get(k) for k in kv}
    for k, v in kv.items():
        if v is None: os.environ.pop(k, None)
        else: os.environ[k] = v
    try: yield
    finally:
        for k, v in old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

sample_res = run_pipeline(SAMPLE_RAW)

def expected_view(df):
    """Project the standardised table to the brief's column layout (ambiguous timestamps shown as REVIEW)."""
    v = df[["Order_ID", "Customer_ID", "Order_TS_UTC", "SKU", "Product", "Qty", "Unit_Price", "Discount", "Currency", "Status"]].copy()
    for c in ["Currency", "Status"]: v[c] = v[c].astype(object)
    v["Order_TS_UTC"] = np.where(df.TS_Status.eq("AMBIGUOUS_NO_TZ"), "REVIEW: ambiguous local time", df.Order_TS_UTC)
    return v.sort_values("Order_ID").reset_index(drop=True)
