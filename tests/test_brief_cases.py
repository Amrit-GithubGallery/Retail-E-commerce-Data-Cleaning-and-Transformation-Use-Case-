"""Tests: brief cases."""
import pandas as pd
from decimal import Decimal
from src.retail_pipeline import analyst_extract, clean_returns, fmt_utc, normalize_order_id, parse_discount, parse_money, parse_timestamp, resolve_customer, resolve_sku
from .helpers import P, TEST_KEY, case, flags_of, mk


# ---------------- brief test cases TC01-TC10 ----------------
@case("TC01", "Whitespace and ID mapping", "' ord-1042 ' + customer alias cust07", "Order ID -> ORD-1042; customer -> CUST-007")
def test_tc01():
    assert normalize_order_id(" ord-1042 ") == "ORD-1042" and resolve_customer("cust07") == ("CUST-007", None)
    r = P(mk(Order_ID=" ord-1042 ", Customer_ID="cust07")).standardized.iloc[0]
    assert (r.Order_ID, r.Customer_ID) == ("ORD-1042", "CUST-007"); return "ORD-1042 / CUST-007"

@case("TC02", "Equivalent timestamp deduplication", "2026-05-14 10:30 -04:00 and 2026-05-14T14:30Z", "Same instant identified; duplicate not double-counted")
def test_tc02():
    a = parse_timestamp("2026-05-14 10:30 -04:00")["utc"]; b = parse_timestamp("2026-05-14T14:30Z")["utc"]
    assert a == b
    r = P(mk(Order_TS="2026-05-14 10:30 -04:00"), mk(Order_TS="2026-05-14T14:30Z"))
    assert r.standardized.Is_Authoritative.sum() == 1 and len(r.superseded) == 1 and r.fulfilled.Net_Minor.sum() == 45000, "double counted"
    return f"same instant {fmt_utc(a)}; 1 kept, 1 superseded; net minor = {r.fulfilled.Net_Minor.sum()}"

@case("TC03", "SKU canonicalization", "mug_blk / Blk Ceramic Mug", "SKU -> MUG-BLK; product name from catalogue")
def test_tc03():
    assert resolve_sku("mug_blk", "Blk Ceramic Mug") == ("MUG-BLK", None)
    r = P(mk(SKU="mug_blk", Product="Blk Ceramic Mug")).standardized.iloc[0]
    assert r.SKU == "MUG-BLK" and r.Product == "Black Ceramic Mug"; return f"{r.SKU} / {r.Product}"

@case("TC04", "Discount normalization", "₹450.00 and 10% discount", "Price 450.00; discount 45.00")
def test_tc04():
    price, hint, issue = parse_money("₹450.00"); assert (price, hint, issue) == (Decimal("450.00"), "INR", None)
    assert parse_discount("10%", price) == (Decimal("45.00"), None)
    r = P(mk(Unit_Price="₹450.00", Discount="10%")).standardized.iloc[0]
    assert (r.Unit_Price, r.Discount, r.Sold_Unit_Price_Minor, r.Sold_Discount_Minor) == (450.0, 45.0, 45000, 4500)
    return "price=450.00, discount=45.00 (45000 / 4500 minor)"

@case("TC05", "Invalid quantity", "Qty = -1 on a new order line", "Flag for review; not silently treated as a sale")
def test_tc05():
    r = P(mk(Qty=-1)); assert "INVALID_QTY" in flags_of(r) and r.standardized.iloc[0].Disposition == "REVIEW"
    assert len(r.clean) == 0 and len(r.fulfilled) == 0; return "flagged INVALID_QTY; review; zero revenue"

@case("TC06", "Ambiguous timestamp", "14-05-2026 09:15 without timezone", "Quarantine or request source timezone; do not invent UTC")
def test_tc06():
    t = parse_timestamp("14-05-2026 09:15"); assert t["status"] == "AMBIGUOUS_NO_TZ" and t["utc"] is None
    r = P(mk(Order_TS="14-05-2026 09:15")).standardized.iloc[0]
    assert r.Disposition == "REVIEW" and pd.isna(r.Order_TS_UTC) and "TS_AMBIGUOUS_NO_TZ" in r.Review_Reasons
    t2 = parse_timestamp("14-05-2026 09:15", assumed_offset_minutes=330)
    assert fmt_utc(t2["utc"]) == "2026-05-14T03:45:00Z" and t2["status"] == "OK_ASSUMED_TZ"
    return "quarantined; resolves to 03:45Z only when source offset +05:30 is supplied"

@case("TC07", "Currency conversion", "USD order without FX rate for date", "Preserve USD amount; flag conversion as unavailable")
def test_tc07():
    row = mk(SKU="BAG-01", Product="Canvas Tote", Unit_Price="$18.00", Currency="USD")
    r = P(row).standardized.iloc[0]
    assert r.Net_Minor == 1800 and r.Currency == "USD" and pd.isna(r.Net_Reporting_Minor) and "FX_UNAVAILABLE" in r.Warnings
    r2 = P(row, fx_rates={("2026-05-14", "USD"): Decimal("83.50")}).standardized.iloc[0]
    assert r2.Net_Reporting_Minor == 150300 and "FX_UNAVAILABLE" not in r2.Warnings
    return "USD 18.00 preserved + FX_UNAVAILABLE; with a dated rate -> 1503.00 INR"

@case("TC08", "Privacy masking", "Customer email in source export", "Mask / tokenize email in analyst-facing output")
def test_tc08():
    r = P(mk(Email="anita.rao@example.com", Phone="+91 98765 43210")); row = r.standardized.iloc[0]
    assert row.Email_Masked == "a***@example.com" and row.Phone_Masked.endswith("10") and "*" in row.Phone_Masked
    blob = " ".join(map(str, r.standardized.astype(str).values.ravel()))
    assert "anita.rao@example.com" not in blob and "98765" not in blob, "raw PII leaked"
    ext = analyst_extract(r.standardized, key=TEST_KEY)
    assert "Customer_ID" not in ext.columns and ext.Customer_Token.notna().all()
    return f"{row.Email_Masked} | {row.Phone_Masked} | token={ext.Customer_Token.iloc[0]}"

@case("TC09", "Return linkage", "Return references an unknown order line", "Unmatched-return exception; excluded from linked metrics")
def test_tc09():
    base = P(mk(Order_ID="ORD-3001"))
    rr = pd.DataFrame([["RET-X", "ORD-9999", "MUG-BLK", 1, "damaged", "450", "INR"]], columns=["Return ID", "Order ID", "SKU", "Qty", "Reason", "Refund", "Currency"])
    ret, exc = clean_returns(rr, base.standardized)
    assert "RETURN_UNMATCHED_LINE" in set(exc.Flag) and (ret.Link_Status == "LINKED").sum() == 0; return "RETURN_UNMATCHED_LINE; 0 linked"

@case("TC10", "Cancelled order revenue", "Status = cancelled", "Excluded from fulfilled net sales")
def test_tc10():
    for s in ("cancelled", "Canceled"):
        r = P(mk(Status=s)); assert r.standardized.iloc[0].Status == "CANCELLED" and r.standardized.iloc[0].Revenue_Class == "EXCLUDED" and len(r.fulfilled) == 0
    return "CANCELLED -> EXCLUDED; fulfilled net = 0"
