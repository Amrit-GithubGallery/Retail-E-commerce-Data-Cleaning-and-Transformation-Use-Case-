"""Tests: timestamps."""
from src.retail_pipeline import RefData, demo_reference, fmt_utc, infer_date_order, parse_timestamp
from .helpers import P, case, mk


# ---------------- limitation fix 2: dates ----------------
@case("D01", "Declared date order", "05/06/2026 10:00 +00:00", "Ambiguous without a declaration; resolved and marked when declared")
def test_d01():
    s = "05/06/2026 10:00 +00:00"; assert parse_timestamp(s)["status"] == "AMBIGUOUS_DATE_ORDER"
    a, b = parse_timestamp(s, date_order="DMY"), parse_timestamp(s, date_order="MDY")
    assert fmt_utc(a["utc"]) == "2026-06-05T10:00:00Z" and fmt_utc(b["utc"]) == "2026-05-06T10:00:00Z" and a["status"] == "OK_ASSUMED_ORDER"
    assert parse_timestamp("25/12/2026 10:00 +00:00", date_order="MDY")["status"] == "INVALID", "declared order contradicted by data"
    r = P(mk(Order_TS=s), date_order="DMY").standardized.iloc[0]; assert "TS_DATE_ORDER_ASSUMED" in r.Warnings and r.Disposition == "CLEAN"; return "ok"

@case("D02", "Evidence-based date order", "columns with one-sided / no / conflicting evidence", "Infer only from one-sided evidence; otherwise stay quarantined")
def test_d02():
    assert infer_date_order(["05/06/2026 1:00", "25/12/2026 9:00"])[0] == "DMY" and infer_date_order(["12/25/2026 9:00", "05/06/2026 1:00"])[0] == "MDY"
    assert infer_date_order(["05/06/2026 1:00", "07/08/2026 1:00"])[0] is None and infer_date_order(["25/12/2026 9:00", "12/25/2026 9:00"])[0] is None
    r = P(mk(Order_TS="05/06/2026 10:00 +00:00"), mk(Order_ID="ORD-9002", Order_TS="25/12/2026 10:00 +00:00"), date_order="infer")
    assert r.date_order_decision[0] == "DMY" and r.standardized.Disposition.astype(str).tolist() == ["CLEAN", "CLEAN"]
    r2 = P(mk(Order_TS="05/06/2026 10:00 +00:00"), date_order="infer"); assert r2.standardized.iloc[0].Disposition == "REVIEW"; return "ok"

@case("D03", "DST-safe source time zone", "Europe/London summer, winter, spring gap, autumn fold", "Offset follows DST; gap/fold quarantined, never guessed")
def test_d03():
    z = lambda s: parse_timestamp(s, source_tz="Europe/London")
    assert fmt_utc(z("2026-07-01 10:00")["utc"]) == "2026-07-01T09:00:00Z" and fmt_utc(z("2026-01-15 10:00")["utc"]) == "2026-01-15T10:00:00Z"
    assert z("2026-03-29 01:30")["status"] == "NONEXISTENT_DST" and z("2026-10-25 01:30")["status"] == "AMBIGUOUS_DST"
    assert fmt_utc(parse_timestamp("2026-07-01 10:00 +05:30", source_tz="Europe/London")["utc"]) == "2026-07-01T04:30:00Z", "explicit offset must win"
    r = P(mk(Order_TS="2026-10-25 01:30"), ref=RefData(demo_reference().catalogue, demo_reference().customers, source_tz="Europe/London"))
    assert "TS_DST_AMBIGUOUS" in r.standardized.iloc[0].Review_Reasons; return "ok"

@case("D04", "Flexible formats and argument safety", "M/D/YYYY, dd.mm.yyyy, 1-digit parts; both tz arguments", "Parsed when unambiguous; conflicting options rejected")
def test_d04():
    assert fmt_utc(parse_timestamp("5/14/2026 9:05", source_tz="UTC")["utc"]) == "2026-05-14T09:05:00Z"
    assert fmt_utc(parse_timestamp("14.05.2026 09:15 +05:30")["utc"]) == "2026-05-14T03:45:00Z" and fmt_utc(parse_timestamp("2026-5-4 9:05:07Z")["utc"]) == "2026-05-04T09:05:07Z"
    try: parse_timestamp("2026-05-14 10:00", assumed_offset_minutes=0, source_tz="UTC"); raise AssertionError("accepted")
    except ValueError: pass
    return "ok"
