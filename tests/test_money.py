"""Tests: money."""
from decimal import Decimal
from .helpers import P, case, flags_of, mk


# ---------------- limitation fix 3: exact money ----------------
@case("M01", "Exact minor-unit money", "1000 lines of 0.10", "Exact integer total 10000 minor units; display equals it")
def test_m01():
    rows = [mk(Order_ID=f"ORD-{i:05d}", Unit_Price="0.10") for i in range(1, 1001)]
    r = P(*rows); assert int(r.fulfilled.Net_Minor.sum()) == 10000 and int(r.fulfilled.Gross_Minor.sum()) == 10000
    assert (r.standardized.Net - r.standardized.Net_Minor / 100).abs().max() < 1e-9; return "Net_Minor sum == 10000 exactly"

@case("M02", "Silent precision loss", "price 0.125 and 0.001", "Rounding half-up is flagged; a price that rounds to 0 is invalid")
def test_m02():
    r = P(mk(Unit_Price=0.125)).standardized.iloc[0]; assert r.Sold_Unit_Price_Minor == 13 and "PRICE_ROUNDED" in r.Warnings
    assert "INVALID_PRICE" in flags_of(P(mk(Unit_Price=0.001))); return "0.125 -> 0.13 flagged"

@case("M03", "FX rounding in minor units", "net 1.00 USD x 83.505", "Half-up on integer minor units: 8351")
def test_m03():
    r = P(mk(Unit_Price="1.00", Currency="USD"), fx_rates={("2026-05-14", "USD"): Decimal("83.505")}).standardized.iloc[0]
    assert r.Net_Reporting_Minor == 8351; return "100 x 83.505 = 8350.5 -> 8351"
