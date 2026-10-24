"""Tests: payments shipments."""
import pandas as pd
from src.retail_pipeline import clean_payments, clean_shipments, fulfilment_performance, payment_rates, reconcile_payments
from .helpers import P, case, mk


def _pay_fixture():
    base = P(mk(Order_ID="ORD-1", Unit_Price="1000", Shipping=200), mk(Order_ID="ORD-2", Unit_Price="500", Shipping=100),
             mk(Order_ID="ORD-3", Unit_Price="300"), mk(Order_ID="ORD-4", Unit_Price="100", Shipping=0), mk(Order_ID="ORD-5", Unit_Price="100", Shipping=0))
    pay = pd.DataFrame([["P1", "ORD-1", "Credit Card", "captured", "1200"], ["P2", "ORD-2", "UPI", "captured", "500"],
                        ["P3", "ORD-3", "wallet", "failed", "300"], ["P4", "ORD-3", "wallet", "failed", "300"], ["P5", "ORD-3", "wallet", "declined", "300"], ["P6", "ORD-3", "card", "captured", "300"],
                        ["P7", "ORD-404", "card", "captured", "10"], ["P8", "ORD-4", "crypto", "weird", "100"], ["P9", "ORD-5", "voucher", "captured", "0"]],
                       columns=["Payment ID", "Order ID", "Method", "Status", "Amount"])
    return base, pay

@case("P01", "Payments normalisation and linkage", "methods, statuses, unmatched order, 3 failures, zero amount", "Vocabulary applied; problems flagged; repeated failures surfaced")
def test_p01():
    base, pay = _pay_fixture(); p, e = clean_payments(pay, base.standardized)
    assert p.set_index("Payment_ID").loc["P1", "Method"] == "CARD" and p.set_index("Payment_ID").loc["P5", "Status"] == "FAILED"
    fl = set(e.Flag); assert {"PAYMENT_UNMATCHED_ORDER", "PAYMENT_METHOD_UNMAPPED", "PAYMENT_STATUS_UNKNOWN", "PAYMENT_ZERO_AMOUNT", "REPEATED_FAILED_PAYMENTS"} <= fl, fl
    assert p.set_index("Payment_ID").loc["P7", "Link_Status"] == "EXCEPTION"; return "ok"

@case("P02", "Payment reconciliation", "paid == net + shipping | paid less | unknown component", "Exact match / PAID_LESS / NO_ORDER_TOTAL")
def test_p02():
    base, pay = _pay_fixture(); p, _ = clean_payments(pay, base.standardized)
    r = reconcile_payments(p, base.standardized, components=("Net_Minor", "Shipping_Minor")).set_index("Order_ID").Recon_Status
    assert r["ORD-1"] == "MATCH" and r["ORD-2"] == "PAID_LESS" and r["ORD-3"] == "NO_ORDER_TOTAL"; return "ok"

@case("P03", "Payment rates", "CAPTURED/FAILED mix by method", "Rates over recorded final statuses only")
def test_p03():
    pay = pd.DataFrame({"Link_Status": "LINKED", "Method": ["CARD"] * 4 + ["UPI"], "Status": ["CAPTURED", "CAPTURED", "FAILED", "PENDING", "NOT_RECORDED"]})
    r = payment_rates(pay).set_index("Method"); assert r.loc["CARD", "Attempts"] == 3 and r.loc["CARD", "Failure_Rate_%"] == 33.3 and "UPI" not in r.index; return "ok"

@case("SH01", "Shipments", "carrier, tracking, chronology, lead time, on-time", "Normalised; impossible chronology excluded from metrics")
def test_sh01():
    base = P(mk(Order_ID="ORD-1"), mk(Order_ID="ORD-2"), mk(Order_ID="ORD-3"))
    ship = pd.DataFrame([["ORD-1", "UPS", "1Z999AA10123456784", "delivered", "2026-05-15T10:00:00Z", "2026-05-17T10:00:00Z", "2026-05-18T10:00:00Z"],
                         ["ORD-2", "Blue Dart", "12", "Delivered", "2026-05-16T10:00:00Z", "2026-05-15T10:00:00Z", "2026-05-18T10:00:00Z"],
                         ["ORD-3", "Moon Express", None, "teleported", "2026-05-15T10:00:00Z", None, None], ["ORD-9", "UPS", None, None, None, None, None]],
                        columns=["Order ID", "Carrier", "Tracking ID", "Status", "Shipped TS", "Delivered TS", "Promised TS"])
    s, e = clean_shipments(ship, base.standardized); assert s.iloc[0].Ship_to_Delivery_Days == 2.0 and s.iloc[0].On_Time is True and s.iloc[0].Tracking_Valid
    assert not s.iloc[1].Metrics_Eligible and not s.iloc[1].Tracking_Valid and pd.isna(s.iloc[1].Ship_to_Delivery_Days)
    assert {"DELIVERED_BEFORE_SHIPPED", "CARRIER_UNMAPPED", "SHIP_STATUS_UNKNOWN", "SHIPMENT_UNMATCHED_ORDER", "TRACKING_INVALID"} <= set(e.Flag)
    f = fulfilment_performance(s); assert f.set_index("Carrier").loc["UPS", "On_Time_Rate_Pct"] == 100.0; return "ok"
