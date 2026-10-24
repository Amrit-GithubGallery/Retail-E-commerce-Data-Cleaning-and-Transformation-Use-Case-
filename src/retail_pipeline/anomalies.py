"""Anomaly detection (robust baselines, order spikes, refund ratios)."""

import numpy as np
import pandas as pd


def robust_anomalies(series, window=28, k=3.5, min_periods=14, scale_floor_pct=0.10):
    """Trailing-baseline anomaly flags for a time-indexed series. scale = max(1.4826*MAD, floor% of |median|, 1e-9)."""
    s = series.sort_index().astype(float); prior = s.shift(1)
    med = prior.rolling(window, min_periods=min_periods).median()
    mad = prior.rolling(window, min_periods=min_periods).apply(lambda x: np.median(np.abs(x - np.median(x))), raw=True)
    scale = np.maximum(np.maximum(1.4826 * mad, scale_floor_pct * med.abs()), 1e-9)
    z = (s - med) / scale
    flag = np.where(med.isna(), "NO_BASELINE", np.where(z > k, "ANOMALY_HIGH", np.where(z < -k, "ANOMALY_LOW", "OK")))
    return pd.DataFrame({"Value": s, "Baseline_Median": med, "Scale": scale, "Z": z, "Flag": flag})

def daily_metric_anomalies(fulfilled, metric="Net_Minor", **kw):
    """Scenario 13/16: daily sales (or discount/refund) vs trailing baseline. Missing calendar days are treated as zero (documented)."""
    d = fulfilled.assign(Day=pd.to_datetime(fulfilled.Order_TS_UTC.str[:10]))
    s = d.groupby("Day")[metric].sum(min_count=1)
    return robust_anomalies(s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D"), fill_value=0), **kw)

def order_spikes(std, max_orders_per_day=5):
    """Scenario 16: customers placing more than N distinct orders in a UTC day (authoritative rows with a known customer)."""
    a = std[std.Is_Authoritative & std.Customer_ID.notna() & std.Order_TS_UTC.notna()]
    g = a.assign(Day=a.Order_TS_UTC.str[:10]).groupby(["Customer_ID", "Day"], observed=True).Order_ID.nunique().rename("Orders").reset_index()
    return g[g.Orders > max_orders_per_day].sort_values("Orders", ascending=False)

def refund_ratio_flags(fulfilled, returns_linked, by="SKU", min_units=20, ratio=0.30):
    """Scenario 16: unusually high refund ratios; groups below `min_units` are reported as INSUFFICIENT_VOLUME, not judged."""
    sold = fulfilled.groupby(by, observed=True).Qty.sum().rename("Units_Sold")
    ret = returns_linked.groupby(by).Return_Qty.sum().rename("Units_Returned")
    d = pd.concat([sold, ret], axis=1).fillna(0); d["Return_Rate"] = d.Units_Returned / d.Units_Sold
    d["Flag"] = np.where(d.Units_Sold < min_units, "INSUFFICIENT_VOLUME", np.where(d.Return_Rate > ratio, "HIGH_REFUND_RATIO", "OK"))
    return d.reset_index()
