"""Tests: geography promotions."""
import numpy as np
import pandas as pd
from src.retail_pipeline import RefData, demo_reference, normalize_postal, normalize_state, promotion_summary
from .helpers import P, case, mk


# ---------------- limitation fix 6: geography, promotions, payments, shipments, events, anomalies ----------------
@case("G01", "State and postal code", "IN / US / BR / GB codes; state names", "Valid -> canonical; invalid flagged; no zero-padding guess")
def test_g01():
    assert normalize_postal("700 001", "IN") == ("700001", None) and normalize_postal("70001", "IN")[1] == "POSTAL_INVALID"
    assert normalize_postal("02134", "US") == ("02134", None) and normalize_postal("2134", "US")[1] == "POSTAL_INVALID"
    assert normalize_postal("01310100", "BR") == ("01310-100", None) and normalize_postal("sw1a1aa", "GB") == ("SW1A 1AA", None)
    assert normalize_state("West Bengal", "IN")[0] == "WB" and normalize_state("São Paulo", "BR")[0] == "SP" and normalize_state("tx", "US")[0] == "TX"
    assert normalize_state("Narnia", "US")[1] == "STATE_UNMAPPED"
    r = P(mk(Country="India", State="West Bengal", Postal_Code="700001")).standardized.iloc[0]; assert (r.State, r.Postal_Code) == ("WB", "700001"); return "ok"

@case("PR01", "Promotion codes", "applied / expired / rejected / unknown", "Four distinct statuses, none silently dropped")
def test_pr01():
    promos = pd.DataFrame({"code": ["SAVE-10", "OLD5", "BIG"], "valid_from": ["2026-05-01"] * 3, "valid_to": ["2026-06-30", "2026-05-10", "2026-12-31"],
                           "min_gross_minor": [np.nan, np.nan, 100000]})
    ref = RefData(demo_reference().catalogue, demo_reference().customers, promotions=promos)
    r = P(mk(Order_ID="ORD-9001", Promo_Code="save 10", Discount="45"), mk(Order_ID="ORD-9002", Promo_Code="OLD5"), mk(Order_ID="ORD-9003", Promo_Code="BIG"),
          mk(Order_ID="ORD-9004", Promo_Code="NOPE"), mk(Order_ID="ORD-9005"), mk(Order_ID="ORD-9006", Promo_Code="SAVE10", Discount="0"), ref=ref).standardized
    assert r.Promo_Status.astype(str).tolist() == ["APPLIED", "EXPIRED", "REJECTED", "UNKNOWN_CODE", "NONE", "APPLIED"]
    assert "PROMO_NO_DISCOUNT" in r.iloc[5].Warnings; assert len(promotion_summary(r)) == 4; return "ok"
