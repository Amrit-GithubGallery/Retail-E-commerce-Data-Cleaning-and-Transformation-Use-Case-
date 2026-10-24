"""Tests: analytics."""
import pandas as pd
from src.retail_pipeline import clv_historical, cohort_analysis, funnel
from .helpers import P, case, mk


@case("T01", "Cohorts, repeat rate, funnel, CLV", "3 customers over 2 months; 4-stage funnel", "Hand-computed values")
def test_t01():
    rows = [mk(Order_ID="ORD-1", Customer_ID="cust-7", Order_TS="2026-01-10T10:00:00Z"), mk(Order_ID="ORD-2", Customer_ID="cust-7", Order_TS="2026-02-10T10:00:00Z"),
            mk(Order_ID="ORD-3", Customer_ID="cust-8", Order_TS="2026-01-20T10:00:00Z"), mk(Order_ID="ORD-4", Customer_ID="cust-9", Order_TS="2026-02-05T10:00:00Z")]
    f = P(*rows).fulfilled; s, ret = cohort_analysis(f); s = s.set_index(s.Cohort.astype(str))
    assert s.loc["2026-01", "Customers"] == 2 and s.loc["2026-01", "Repeat_Rate_%"] == 50.0 and ret.loc[pd.Period("2026-01"), 1] == 1
    ev = pd.DataFrame({"Session_ID": ["a", "a", "a", "b", "b", "c", "d"], "Stage": ["session", "cart", "order", "session", "order", "session", "cart"]})
    st = funnel(ev, ["session", "cart", "order"]).Units.tolist(); lo = funnel(ev, ["session", "cart", "order"], strict=False).Units.tolist()
    assert st == [3, 1, 1] and lo == [3, 2, 2]
    c, sm = clv_historical(f); assert sm.iloc[0].Customers == 3 and sm.iloc[0].Mean_Hist_Value == 600.0; return "ok"
