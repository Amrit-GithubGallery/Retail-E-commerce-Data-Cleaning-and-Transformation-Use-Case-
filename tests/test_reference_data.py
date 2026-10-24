"""Tests: reference data."""
import os
import pandas as pd
import tempfile
from src.retail_pipeline import RefData, derive_reference, fx_coverage, load_fx_rates, numeric_customer_normalizer, order_id_rule, run_pipeline
from .helpers import P, case, flags_of, mk


# ---------------- limitation fix 1: reference data ----------------
def _gbp_ref():
    cat = pd.DataFrame({"SKU": ["85048", "79323P"], "Product": ["15CM GLASS BALL", "PINK CHERRY LIGHTS"]})
    return RefData(cat, {"CUST-13085"}, customer_normalizer=numeric_customer_normalizer(), order_id_normalizer=order_id_rule(r"C?\d{6}"),
                   currencies=("GBP",), reporting_currency="GBP", source_tz="Europe/London", name="uk-test")

@case("R01", "Pluggable reference data", "custom catalogue / customers / GBP / ID rule / source tz", "Same code runs against another master; unknown keys still flagged")
def test_r01():
    ref = _gbp_ref()
    row = {"Order ID": "489434", "Customer ID": "13085.0", "Order TS": "2026-07-01 08:00:00", "SKU": "85048", "Product": "x", "Qty": 2,
           "Unit Price": 6.95, "Discount": 0, "Currency": "GBP", "Status": "Delivered"}
    r = run_pipeline(pd.DataFrame([row, {**row, "Order ID": "489435", "SKU": "NOPE", "Customer ID": "99999"}]), ref=ref).standardized
    a = r.iloc[0]; assert a.Disposition == "CLEAN" and a.Customer_ID == "CUST-13085" and a.Net_Minor == 1390 and a.Order_TS_UTC == "2026-07-01T07:00:00Z"
    assert "SKU_UNKNOWN" in r.iloc[1].Review_Reasons and "CUSTOMER_UNMATCHED" in r.iloc[1].Warnings
    assert "SKU_UNKNOWN" in flags_of(run_pipeline(pd.DataFrame([row]))), "default reference must not know this SKU"
    return "custom master resolves; BST 08:00 -> 07:00Z; unknown SKU/customer flagged"

@case("R02", "Reference integrity + derived reference", "supplier key not in reference table; derive from data", "Bad masters rejected; derived masters labelled derived")
def test_r02():
    try: RefData(pd.DataFrame({"SKU": ["A"], "Product": ["a"], "Supplier": ["S9"]}), set(), suppliers={"S1"}); raise AssertionError("bad supplier accepted")
    except ValueError: pass
    d = pd.DataFrame({"S": ["a1", "A1", "b2"], "N": ["Red Mug", "Red Mug", "Blue Cup"], "C": ["1.0", "2", None]})
    ref = derive_reference(d, "S", "N", "C"); assert ref.derived and set(ref.cat) == {"A1", "B2"} and ref.cat["A1"]["Product"] == "Red Mug" and ref.customers == {"CUST-1", "CUST-2"}
    return "ok"

@case("R03", "FX loader and coverage", "CSV with duplicate rate; missing date", "Invalid FX files rejected; coverage gap listed")
def test_r03():
    with tempfile.TemporaryDirectory() as t:
        p = os.path.join(t, "fx.csv"); open(p, "w").write("date,currency,rate\n2026-05-14,USD,83.5\n2026-05-14,USD,83.6\n")
        try: load_fx_rates(p); raise AssertionError("duplicate accepted")
        except ValueError: pass
        open(p, "w").write("date,currency,rate\n2026-05-14,USD,83.5\n"); fx = load_fx_rates(p)
    row = mk(SKU="BAG-01", Product="Canvas Tote", Unit_Price="$18", Currency="USD")
    r = P(row, mk(Order_ID="ORD-9002", Order_TS="2026-05-15T10:00:00Z", SKU="BAG-01", Product="Canvas Tote", Unit_Price="$18", Currency="USD"), fx_rates=fx)
    gap = fx_coverage(r, fx); assert gap.values.tolist() == [["2026-05-15", "USD"]]; return "gap = 2026-05-15 USD"
