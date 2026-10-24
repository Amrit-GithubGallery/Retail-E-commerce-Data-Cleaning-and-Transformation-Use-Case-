"""Tests: events anomalies."""
import pandas as pd
from src.retail_pipeline import order_spikes, reconcile_events, refund_ratio_flags, robust_anomalies
from .helpers import P, case, mk


@case("E01", "Out-of-order / late events", "DELIVERED ingested before SHIPPED; delivered stamped before shipped", "Lifecycle order wins over arrival order; contradictions flagged")
def test_e01():
    ev = pd.DataFrame([["O1", "ORDERED", "2026-05-01T10:00Z", "2026-05-01T10:01Z"], ["O1", "DELIVERED", "2026-05-04T10:00Z", "2026-05-04T10:05Z"], ["O1", "SHIPPED", "2026-05-02T10:00Z", "2026-05-06T10:00Z"],
                       ["O2", "SHIPPED", "2026-05-03T10:00Z", "2026-05-03T10:00Z"], ["O2", "DELIVERED", "2026-05-02T10:00Z", "2026-05-04T10:00Z"]],
                      columns=["Order_ID", "Event_Type", "Event_TS", "Ingested_At"])
    e, st = reconcile_events(ev); st = st.set_index("Order_ID")
    assert st.loc["O1", "Reconciled_Status"] == "DELIVERED" and st.loc["O1", "Last_Arrived_Status"] == "SHIPPED" and st.loc["O1", "Naive_Would_Be_Wrong"]
    assert "LATE_ARRIVING" in e.iloc[2].Flags and "ARRIVED_OUT_OF_ORDER" in e.iloc[2].Flags and "EVENT_BEFORE_PREDECESSOR" in e.iloc[4].Flags and st.loc["O2", "Has_Contradiction"]
    return "ok"

@case("A01", "Anomaly detection with baselines", "flat 100/day + one spike; short history", "Spike flagged; early days NO_BASELINE; no verdict without history")
def test_a01():
    s = pd.Series([100.0 + (i % 3) for i in range(40)], index=pd.date_range("2026-01-01", periods=40)); s.iloc[30] = 1000
    a = robust_anomalies(s); assert a.Flag.iloc[30] == "ANOMALY_HIGH" and (a.Flag.iloc[:14] == "NO_BASELINE").all() and (a.Flag.iloc[14:30] == "OK").all() and a.Flag.iloc[31] == "OK"
    assert (robust_anomalies(pd.Series([5.0] * 10)).Flag == "NO_BASELINE").all(); return "ok"

@case("A02", "Order spikes and refund ratios", "7 orders/day customer; 40% return rate on 50 units, on 5 units", "Flag volume spikes; small samples not judged")
def test_a02():
    r = P(*[mk(Order_ID=f"ORD-{i}") for i in range(1, 8)]); assert len(order_spikes(r.standardized, 5)) == 1 and len(order_spikes(r.standardized, 7)) == 0
    f = pd.DataFrame({"SKU": ["A"] * 50 + ["B"] * 5, "Qty": 1}); ret = pd.DataFrame({"SKU": ["A", "B"], "Return_Qty": [20, 4]})
    x = refund_ratio_flags(f, ret).set_index("SKU").Flag; assert x["A"] == "HIGH_REFUND_RATIO" and x["B"] == "INSUFFICIENT_VOLUME"; return "ok"
