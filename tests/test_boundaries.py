"""Tests: boundaries."""
import numpy as np
import pandas as pd
from decimal import Decimal
from src.retail_pipeline import ALL_RAW, clean_returns, fmt_utc, parse_money, parse_timestamp, run_pipeline
from .helpers import P, case, expected_view, flags_of, mk, sample_res


# ---------------- boundary & duplicate tests ----------------
@case("B01", "Quantity boundaries", "qty 0, 1, 1000, 1001, 1.5, null", "Only [1, 1000] integers accepted")
def test_b01():
    assert "INVALID_QTY" in flags_of(P(mk(Qty=0))) and "INVALID_QTY" not in flags_of(P(mk(Qty=1))) and "QTY_OUT_OF_RANGE" not in flags_of(P(mk(Qty=1000)))
    assert "QTY_OUT_OF_RANGE" in flags_of(P(mk(Qty=1001))) and "INVALID_QTY" in flags_of(P(mk(Qty=1.5))) and "INVALID_QTY" in flags_of(P(mk(Qty=None)))
    return "0 invalid | 1, 1000 ok | 1001 out of range | 1.5 / null invalid"

@case("B02", "Discount boundaries", "0, 100%, 450.00 | 100.01%, 450.01, -5, abc", "0 <= discount <= unit price")
def test_b02():
    ok = lambda d: "DISCOUNT_INVALID" not in flags_of(P(mk(Discount=d)))
    assert ok("100%") and ok("450.00") and ok("0") and not ok("100.01%") and not ok("450.01") and not ok("-5") and not ok("abc")
    r = P(mk(Discount="100%")).standardized.iloc[0]; assert r.Discount == 450.0 and r.Net_Minor == 0; return "boundaries correct"

@case("B03", "Timestamp boundaries", "midnight crossing, +05:30, 30-Feb, dd-mm ambiguity, blank", "Correct UTC or explicit status - never a guess")
def test_b03():
    assert fmt_utc(parse_timestamp("2026-05-14 23:30 -04:00")["utc"]) == "2026-05-15T03:30:00Z"
    assert fmt_utc(parse_timestamp("2026-05-15T00:10:00+05:30")["utc"]) == "2026-05-14T18:40:00Z"
    assert fmt_utc(parse_timestamp("2026-05-15T11:00:00+05:30")["utc"]) == "2026-05-15T05:30:00Z"
    assert parse_timestamp("2026-02-30T10:00:00Z")["status"] == "INVALID" and parse_timestamp("12-05-2026 09:15 +05:30")["status"] == "AMBIGUOUS_DATE_ORDER"
    assert parse_timestamp("")["status"] == "MISSING" and parse_timestamp("yesterday")["status"] == "INVALID"; return "ok"

@case("B04", "Duplicate handling - triplicate", "3 identical order lines", "Exactly one authoritative record")
def test_b04():
    r = P(mk(), mk(), mk()); assert r.standardized.Is_Authoritative.sum() == 1 and len(r.superseded) == 2 and r.fulfilled.Net_Minor.sum() == 45000; return "1 kept, 2 superseded"

@case("B05", "Late-arriving update", "same line, event v1 Shipped + v2 Delivered", "Highest event version is authoritative")
def test_b05():
    r = P(mk(Status="Shipped", Event_Version=1), mk(Status="Delivered", Event_Version=2, Order_TS="2026-05-15T10:00:00Z"))
    k = r.standardized[r.standardized.Is_Authoritative].iloc[0]; assert k.Status == "DELIVERED" and k.Event_Version == 2 and len(r.superseded) == 1; return "v2 retained"

@case("B06", "Conflicting duplicates", "same version, qty 1 vs 4", "Flag conflict; do not count either as revenue")
def test_b06():
    r = P(mk(Qty=1), mk(Qty=4)); k = r.standardized[r.standardized.Is_Authoritative].iloc[0]
    assert "CONFLICTING_DUPLICATE" in k.Review_Reasons and k.Disposition == "REVIEW" and len(r.fulfilled) == 0; return "conflict -> review"

@case("B07", "Missing discount", "blank discount", "Do not replace unknown discount with 0")
def test_b07():
    r = P(mk(Discount=None)).standardized.iloc[0]
    assert np.isnan(r.Discount) and pd.isna(r.Net_Minor) and "DISCOUNT_UNKNOWN" in r.Warnings and r.Disposition == "CLEAN"; return "stays NULL"

@case("B08", "Customer ID handling", "blank, CUST-999 (not in master), cust-7", "No arbitrary values; unmatched -> exception queue")
def test_b08():
    r = P(mk(Customer_ID=None), mk(Order_ID="ORD-9002", Customer_ID="CUST-999"), mk(Order_ID="ORD-9003", Customer_ID="cust-7")).standardized
    assert pd.isna(r.Customer_ID.iloc[0]) and "CUSTOMER_ID_MISSING" in r.Warnings.iloc[0]
    assert pd.isna(r.Customer_ID.iloc[1]) and "CUSTOMER_UNMATCHED" in r.Warnings.iloc[1] and r.Customer_ID.iloc[2] == "CUST-007"; return "ok"

@case("B09", "Currency edge cases", "$ with INR, $ with blank, ₹ with blank, XYZ", "Conflicts blocked; no guessing of ambiguous symbols")
def test_b09():
    assert "CURRENCY_SYMBOL_CONFLICT" in flags_of(P(mk(Unit_Price="$10", Currency="INR"))) and "CURRENCY_UNKNOWN" in flags_of(P(mk(Unit_Price="$10", Currency=None)))
    assert "CURRENCY_INFERRED_FROM_SYMBOL" in flags_of(P(mk(Unit_Price="₹10", Currency=None))) and "CURRENCY_UNKNOWN" in flags_of(P(mk(Currency="XYZ"))); return "ok"

@case("B10", "Unit normalisation", "2 dozen, 2 packs (size 3), pack w/o size, 'crate'", "Convert to base unit or flag")
def test_b10():
    r = P(mk(SKU="NOTE-A5", Qty=2, Unit="dozen", Unit_Price="120")).standardized.iloc[0]; assert (r.Qty, r.Unit_Price, r.Gross_Minor) == (24, 10.0, 24000)
    r = P(mk(SKU="NOTE-A5", Qty=2, Unit="pack", Unit_Price="120")).standardized.iloc[0]; assert (r.Qty, r.Unit_Price) == (6, 40.0)
    assert "UNIT_UNKNOWN" in flags_of(P(mk(SKU="MUG-BLK", Unit="pack"))) and "UNIT_UNKNOWN" in flags_of(P(mk(Unit="crate"))); return "ok"

@case("B11", "Order-ID boundaries", "blank, '1042', 'ORD-', null, 'ORD-12A'", "Invalid IDs flagged; valid ones normalised")
def test_b11():
    for bad in ("   ", "1042", "ORD-", None, "ORD-12A"): assert "INVALID_ORDER_ID" in flags_of(P(mk(Order_ID=bad))), repr(bad)
    assert P(mk(Order_ID="ord_0042")).standardized.iloc[0].Order_ID == "ORD-0042"; return "ok"

@case("B12", "Money parsing", "1,299.50 | Rs. 99 | 1.299,50 | abc | 0 | -450", "Numeric decimals or explicit flag")
def test_b12():
    assert parse_money("1,299.50")[0] == Decimal("1299.50") and parse_money("Rs. 99")[0] == Decimal("99.00") and parse_money("R$ 12,5")[2] == "UNPARSEABLE_AMOUNT"
    assert parse_money("1.299,50")[2] == "UNPARSEABLE_AMOUNT" and parse_money("abc")[2] == "UNPARSEABLE_AMOUNT" and parse_money("")[2] == "AMOUNT_MISSING" and parse_money(799)[0] == Decimal("799.00")
    assert "INVALID_PRICE" in flags_of(P(mk(Unit_Price="0"))) and "INVALID_PRICE" in flags_of(P(mk(Unit_Price="-450"))); return "ok"

@case("B13", "Status handling", "'weird', 'Return' (positive qty)", "Unknown / return statuses never counted as revenue")
def test_b13():
    st = P(mk(Status="weird"), mk(Order_ID="ORD-9002", Status="Return")).standardized
    assert "STATUS_UNKNOWN" in st.Review_Reasons.iloc[0] and "RETURN_ON_ORDER_LINE" in st.Review_Reasons.iloc[1]; return "ok"

@case("B14", "Return boundaries", "qty / refund / currency edge cases", "Only consistent returns are linked (exact minor units, cumulative)")
def test_b14():
    base = P(mk(Order_ID="ORD-3001", Qty=2))
    rr = pd.DataFrame([["R1", "ORD-3001", "MUG-BLK", 3, "damaged", "450", "INR"], ["R2", "ORD-3001", "MUG-BLK", 1, "damaged", "900.01", "INR"],
                       ["R3", "ORD-3001", "MUG-BLK", 2, "damaged", "900.00", "INR"], ["R4", "ORD-3001", "MUG-BLK", 1, "damaged", "450", "USD"],
                       ["R5", "ORD-3001", "MUG-BLK", 1, "damaged", "1", "INR"]], columns=["Return ID", "Order ID", "SKU", "Qty", "Reason", "Refund", "Currency"])
    ret, _ = clean_returns(rr, base.standardized)
    assert dict(zip(ret.Return_ID, ret.Link_Status)) == {"R1": "EXCEPTION", "R2": "EXCEPTION", "R3": "LINKED", "R4": "EXCEPTION", "R5": "EXCEPTION"}, ret.Link_Status.tolist()
    return "R3 linked at exact boundary; R5 rejected because R3 already returned everything"

@case("B15", "Reproducibility", "run pipeline twice on identical input", "Identical outputs")
def test_b15():
    r1, r2 = run_pipeline(ALL_RAW), run_pipeline(ALL_RAW)
    assert r1.standardized.astype(str).equals(r2.standardized.astype(str)) and r1.exceptions.equals(r2.exceptions); return "identical"

@case("B16", "End-to-end sample", "4 raw sample rows from the brief", "Matches the brief's expected cleaned dataset")
def test_b16():
    got = expected_view(sample_res.standardized[sample_res.standardized.Is_Authoritative]).to_dict("records")
    exp = [dict(Order_ID="ORD-1042", Customer_ID="CUST-007", Order_TS_UTC="2026-05-14T14:30:00Z", SKU="MUG-BLK", Product="Black Ceramic Mug", Qty=2, Unit_Price=450.0, Discount=45.0, Currency="INR", Status="DELIVERED"),
           dict(Order_ID="ORD-1043", Customer_ID="CUST-008", Order_TS_UTC="REVIEW: ambiguous local time", SKU="TSHIRT-M", Product="Cotton Tee M", Qty=-1, Unit_Price=799.0, Discount=0.0, Currency="INR", Status="RETURN_REVIEW"),
           dict(Order_ID="ORD-1044", Customer_ID="CUST-009", Order_TS_UTC="2026-05-15T05:30:00Z", SKU="BAG-01", Product="Canvas Tote", Qty=1, Unit_Price=18.0, Discount=0.0, Currency="USD", Status="SHIPPED")]
    assert got == exp, f"\n{got}\n!=\n{exp}"; return "matches the brief"
