"""Tests: scale."""
from src.retail_pipeline import ALL_RAW, RefData, demo_reference, run_pipeline
from .helpers import P, case, mk


# ---------------- limitation fix 5: scale ----------------
@case("S00", "Chunked run equivalence", "chunks=1 vs chunks=4 on the demo set", "Identical results; capped audit keeps counts")
def test_s00():
    a = run_pipeline(ALL_RAW).standardized.drop(columns=["Duplicate_Of"]).astype(str).reset_index(drop=True)
    b = run_pipeline(ALL_RAW, chunks=4, audit="capped", audit_cap=2).standardized.drop(columns=["Duplicate_Of"]).astype(str).reset_index(drop=True)
    assert a.equals(b); r = run_pipeline(ALL_RAW, audit="capped", audit_cap=2); assert r.audit.groupby("Field").size().max() <= 3 + len(r.superseded) and r.audit_counts
    return "chunked == single; audit bounded"

@case("S01", "Non-product lines and absent discount field", "POST line; source without discount column", "Fees stay out of product sales; declared policy, not a guess")
def test_s01():
    cat = demo_reference().catalogue
    ref = RefData(cat, demo_reference().customers, non_product={"POST": "POSTAGE"}, discount_policy="ABSENT_IN_SOURCE")
    r = P(mk(SKU="POST", Product="Postage", Discount=None), mk(Order_ID="ORD-9002", Discount=None), ref=ref)
    s = r.standardized; assert s.iloc[0].Revenue_Class == "NON_PRODUCT" and "SKU_UNKNOWN" not in s.iloc[0].Review_Reasons and len(r.fulfilled) == 1
    assert s.iloc[1].Discount_Basis == "NOT_RECORDED_IN_SOURCE" and s.iloc[1].Net_Minor == s.iloc[1].Gross_Minor
    assert P(mk(Discount=None)).standardized.iloc[0].Discount_Basis == "UNKNOWN"; return "ok"
