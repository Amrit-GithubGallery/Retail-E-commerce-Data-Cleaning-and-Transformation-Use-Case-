"""Analytical transformations (sales, AOV, cohorts, funnel, CLV, ...)."""

import numpy as np
import pandas as pd


def _disp(d, cols):
    for c in cols:
        if c in d: d[c.replace("_Minor", "")] = d[c] / 100
    return d

def daily_net_sales(fulfilled, freq="D", by=()):
    """Scenario 1: gross, discounts, net, units, orders by period (D/M), currency and optional dimensions (e.g. by=['Channel'])."""
    f = fulfilled.copy()
    f["Period"] = f.Order_TS_UTC.str[:10] if freq == "D" else f.Order_TS_UTC.str[:7]
    g = (f.groupby(["Period", "Currency", *by], observed=True)
          .agg(Orders=("Order_ID", "nunique"), Units=("Qty", "sum"), Gross_Minor=("Gross_Minor", "sum"),
               Discounts_Minor=("Discount_Total_Minor", "sum"), Net_Minor=("Net_Minor", lambda s: s.sum(min_count=1)),
               Lines_Missing_Net=("Net_Minor", lambda s: int(s.isna().sum()))).reset_index())
    return _disp(g, ["Gross_Minor", "Discounts_Minor", "Net_Minor"])

def product_ranking(fulfilled):
    """Scenario 6: net sales per product, share of net within currency, rank within currency."""
    g = (fulfilled.groupby(["Currency", "SKU", "Product"], observed=True)
         .agg(Units=("Qty", "sum"), Gross_Minor=("Gross_Minor", "sum"), Net_Minor=("Net_Minor", "sum"),
              Lines_Missing_Net=("Net_Minor", lambda s: int(s.isna().sum()))).reset_index())
    tot = g.groupby("Currency", observed=True).Net_Minor.transform("sum")
    g["Share_of_Net_%"] = (g.Net_Minor / tot * 100).round(1)
    g["Rank_in_Currency"] = g.groupby("Currency", observed=True).Net_Minor.rank(ascending=False, method="min").astype(int)
    return _disp(g, ["Gross_Minor", "Net_Minor"]).sort_values(["Currency", "Rank_in_Currency"])

def aov_table(fulfilled):
    """Scenario 2: AOV = net / distinct orders, over orders whose every line has a known net. Items per order = base units / orders."""
    o = (fulfilled.groupby(["Currency", "Order_ID"], observed=True)
         .agg(Items=("Qty", "sum"), Net_Minor=("Net_Minor", "sum"), Lines=("SKU", "count"), Known=("Net_Minor", "count")).reset_index())
    o = o[o.Lines == o.Known]
    a = o.groupby("Currency", observed=True).agg(Orders=("Order_ID", "nunique"), Net_Minor=("Net_Minor", "sum"), Items=("Items", "sum")).reset_index()
    a["AOV"] = (a.Net_Minor / 100 / a.Orders).round(2); a["Items_per_Order"] = (a.Items / a.Orders).round(2)
    return _disp(a, ["Net_Minor"])

def return_rates(fulfilled, returns_linked, by="SKU"):
    """Scenario 7: linked returned units / fulfilled units sold, refund value, by SKU / Supplier."""
    sold = fulfilled.groupby(by, observed=True).agg(Units_Sold=("Qty", "sum")).reset_index()
    r = returns_linked.groupby(by).agg(Units_Returned=("Return_Qty", "sum"), Refund_Minor=("Refund_Minor", "sum")).reset_index()
    a = sold.merge(r, on=by, how="left").fillna({"Units_Returned": 0, "Refund_Minor": 0})
    a["Return_Rate_%"] = (a.Units_Returned / a.Units_Sold * 100).round(1)
    return _disp(a, ["Refund_Minor"])

def cohort_analysis(fulfilled):
    """Scenario 3: cohort = calendar month (UTC) of a customer's first fulfilled order. Repeat rate = customers with >= 2 distinct
    orders / customers. Retention[k] = customers with an order k months after cohort month. Rows without a customer are excluded."""
    d = fulfilled[fulfilled.Customer_ID.notna() & fulfilled.Order_TS_UTC.notna()].copy()
    d["Month"] = pd.PeriodIndex(d.Order_TS_UTC.str[:7], freq="M")
    first = d.groupby("Customer_ID", observed=True).Month.min().rename("Cohort")
    d = d.join(first, on="Customer_ID"); d["Age"] = (d.Month - d.Cohort).map(lambda x: x.n)
    orders = d.groupby("Customer_ID", observed=True).Order_ID.nunique().rename("Orders")
    c = pd.concat([first, orders], axis=1)
    summ = c.groupby("Cohort").agg(Customers=("Orders", "size"), Repeat_Customers=("Orders", lambda s: int((s >= 2).sum())))
    summ["Repeat_Rate_%"] = (summ.Repeat_Customers / summ.Customers * 100).round(1)
    ret = d.groupby(["Cohort", "Age"], observed=True).Customer_ID.nunique().unstack(fill_value=0)
    return summ.reset_index(), ret

def regional_summary(fulfilled, by=("Country",)):
    """Scenario 12: net sales, orders and units by standardised geography (null geography kept as 'UNKNOWN', never imputed)."""
    f = fulfilled.copy()
    for b in by: f[b] = f[b].astype(object).where(f[b].notna(), "UNKNOWN")
    g = f.groupby(["Currency", *by], observed=True).agg(Orders=("Order_ID", "nunique"), Units=("Qty", "sum"),
                                                        Net_Minor=("Net_Minor", lambda s: s.sum(min_count=1))).reset_index()
    return _disp(g, ["Net_Minor"]).sort_values(["Currency", "Net"], ascending=[True, False])

def fulfilment_performance(ship, by="Carrier"):
    """Scenario 8: lead time (ship->delivery), order->delivery time and on-time rate (delivered <= promised), eligible rows only."""
    e = ship[ship.Metrics_Eligible].copy(); e[by] = e[by].astype(object).where(e[by].notna(), "UNKNOWN")
    g = e.groupby(by).agg(Shipments=("Order_ID", "size"), Avg_Ship_to_Delivery_Days=("Ship_to_Delivery_Days", "mean"),
                          Median_Order_to_Delivery_Days=("Order_to_Delivery_Days", "median"),
                          On_Time_Rate_Pct=("On_Time", lambda s: np.nan if s.notna().sum() == 0 else round(s.dropna().astype(bool).mean() * 100, 1)),
                          Judged_On_Time=("On_Time", "count")).round(2).reset_index()
    g["Excluded_Ineligible"] = len(ship) - len(e)
    return g

def payment_rates(pay, by="Method"):
    """Scenario 10: authorisation / capture / failure rates over attempts with a recorded final-ish status
    (CAPTURED, AUTHORIZED, REFUNDED, VOIDED, FAILED). PENDING / NOT_RECORDED / UNKNOWN are excluded from denominators."""
    p = pay[pay.Link_Status == "LINKED"].copy(); p[by] = p[by].where(p[by].notna(), "UNKNOWN")
    judged = p[p.Status.isin(["CAPTURED", "AUTHORIZED", "REFUNDED", "VOIDED", "FAILED"])]
    if judged.empty: return pd.DataFrame({by: [], "Note": []})
    ct = judged.groupby([by, "Status"]).size().unstack(fill_value=0)
    for c in ["CAPTURED", "AUTHORIZED", "REFUNDED", "VOIDED", "FAILED"]:
        if c not in ct: ct[c] = 0
    n = ct.sum(axis=1)
    out = pd.DataFrame({"Attempts": n, "Authorization_Rate_%": ((n - ct.FAILED) / n * 100).round(1),
                        "Capture_Rate_%": ((ct.CAPTURED + ct.REFUNDED) / n * 100).round(1), "Failure_Rate_%": (ct.FAILED / n * 100).round(1)})
    return out.reset_index()

def funnel(events, stages, unit_col="Session_ID", stage_col="Stage", strict=True):
    """Scenario 4: distinct units (sessions/visitors) reaching each stage. strict=True counts a unit at stage k only if it also
    reached every earlier stage; strict=False counts any unit that has the stage. Step conversion = n_k / n_(k-1)."""
    reached = {s: set(events.loc[events[stage_col] == s, unit_col]) for s in stages}
    n, prev = [], None
    for s in stages:
        cur = reached[s] if (not strict or prev is None) else reached[s] & prev
        n.append(len(cur)); prev = cur
    out = pd.DataFrame({"Stage": stages, "Units": n})
    out["Step_Conversion_%"] = (out.Units / out.Units.shift(1) * 100).round(1)
    out["Overall_Conversion_%"] = (out.Units / out.Units.iloc[0] * 100).round(1) if out.Units.iloc[0] else np.nan
    return out

def clv_historical(fulfilled):
    """Scenario 11 (documented method): HISTORICAL realised value = sum of fulfilled net sales per customer to date (not predictive).
    Reports per currency; also order count, tenure in days and the share of revenue from the top 10% of customers."""
    d = fulfilled[fulfilled.Customer_ID.notna()]
    c = d.groupby(["Currency", "Customer_ID"], observed=True).agg(Orders=("Order_ID", "nunique"), Net_Minor=("Net_Minor", "sum"),
                                                                    First=("Order_TS_UTC", "min"), Last=("Order_TS_UTC", "max")).reset_index()
    c = c[c.Orders > 0]
    c["Tenure_Days"] = (pd.to_datetime(c.Last.str[:10]) - pd.to_datetime(c.First.str[:10])).dt.days
    def top10(s): k = max(1, int(np.ceil(len(s) * 0.1))); return round(s.nlargest(k).sum() / s.sum() * 100, 1) if s.sum() else np.nan
    s = c.groupby("Currency", observed=True).agg(Customers=("Customer_ID", "size"), Mean_Orders=("Orders", "mean"),
                                                 Mean_Hist_Value_Minor=("Net_Minor", "mean"), Median_Hist_Value_Minor=("Net_Minor", "median"),
                                                 Top10pct_Share_of_Net_=("Net_Minor", top10)).reset_index()
    s["Mean_Hist_Value"] = (s.Mean_Hist_Value_Minor / 100).round(2); s["Median_Hist_Value"] = (s.Median_Hist_Value_Minor / 100).round(2)
    return c, s

def promotion_summary(std):
    """Scenario 12 / 5: redemption lines and discount cost by promo code and status. Incremental sales are NOT computed:
    they need a holdout or counterfactual baseline that order data alone cannot provide."""
    a = std[std.Is_Authoritative & (std.Promo_Status != "NONE")]
    g = a.groupby(["Promo_Code", "Promo_Status"], observed=True).agg(Lines=("Raw_Row_ID", "size"), Orders=("Order_ID", "nunique"),
        Gross_Minor=("Gross_Minor", "sum"), Discount_Cost_Minor=("Discount_Total_Minor", "sum")).reset_index()
    return _disp(g, ["Gross_Minor", "Discount_Cost_Minor"])
