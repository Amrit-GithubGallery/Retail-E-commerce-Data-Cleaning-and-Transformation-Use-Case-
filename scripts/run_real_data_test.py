
"""Run the pipeline on real datasets and write evidence to ./real_data_results/.

Usage:
    python scripts/run_real_data_test.py --olist DIR_WITH_OLIST_CSVS --retail2 online_retail_II.csv [--out real_data_results]

Download:
    Olist -> kaggle.com/datasets/olistbr/brazilian-ecommerce
    Online Retail II -> archive.ics.uci.edu/dataset/502
"""

import argparse
import os
import sys
import time
import json

try:
    import resource
except ImportError:
    resource = None

import psutil
import numpy as np
import pandas as pd

import retail_pipeline as rp
from retail_pipeline import adapters as A


def mem_mb():
    """Return process memory in MB.

    On Linux/macOS, return peak resident memory.
    On Windows, return current resident memory because resource
    is unavailable there.
    """
    if resource is not None:
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

        # Linux reports KB; macOS reports bytes.
        if sys.platform == "darwin":
            return usage / (1024 * 1024)

        return usage / 1024

    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)


def run_online_retail(csv, out, chunks=8):
    os.makedirs(out, exist_ok=True)

    S = {
        "dataset": "Online Retail II (UCI 502)"
    }

    # Load and adapt the source dataset.
    t = time.time()
    fr, ref = A.online_retail_frames(csv)
    S["adapter_s"] = round(time.time() - t, 1)

    raw = fr["orders"]

    S["raw_rows_total"] = int(
        len(raw) + fr["credit_rows"]
    )
    S["sales_rows"] = int(len(raw))
    S["credit_note_rows"] = int(fr["credit_rows"])

    # Run the main pipeline.
    t = time.time()

    res = rp.run_pipeline(
        raw,
        ref=ref,
        chunks=chunks,
        audit="capped",
        audit_cap=2000,
        slim=True,
        aggregate_assumption_flags=True,
    )

    elapsed = time.time() - t

    S["pipeline_s"] = round(elapsed, 1)
    S["rows_per_s"] = (
        int(len(raw) / elapsed) if elapsed > 0 else 0
    )
    S["peak_mem_mb"] = round(mem_mb(), 1)

    std = res.standardized

    S["disposition"] = (
        std.Disposition.astype(str)
        .value_counts()
        .to_dict()
    )

    S["top_flags"] = (
        res.exceptions
        .groupby(["Severity", "Flag"])
        .size()
        .sort_values(ascending=False)
        .head(12)
        .to_dict()
        .__repr__()
    )

    S["ts_status"] = (
        std.TS_Status.astype(str)
        .value_counts()
        .to_dict()
    )

    # Clean and link credit notes.
    ret, rex = rp.clean_returns(
        fr["returns"],
        std,
        ref,
    )

    S["credit_notes_linked"] = int(
        (ret.Link_Status == "LINKED").sum()
    )
    S["credit_notes_total"] = int(len(ret))

    # Data quality report.
    dq = rp.dq_report(
        raw,
        res,
        ret,
        rex,
        ref,
    )

    S["dq_fail"] = int((dq.Status == "FAIL").sum())
    S["dq_warn"] = int((dq.Status == "WARN").sum())
    S["dq_pass"] = int((dq.Status == "PASS").sum())

    # Analytics.
    f = res.fulfilled

    daily = rp.daily_net_sales(f, "M")
    prod = rp.product_ranking(f)
    aov = rp.aov_table(f)
    coh, ret_m = rp.cohort_analysis(f)
    reg = rp.regional_summary(f)

    clv_c, clv_s = rp.clv_historical(f)
    an = rp.daily_metric_anomalies(f)

    S["net_sales_gbp_total"] = round(
        float(f.Net_Minor.sum()) / 100,
        2,
    )

    S["fulfilled_lines"] = int(len(f))

    S["aov"] = aov[
        ["Orders", "AOV", "Items_per_Order"]
    ].to_dict("records")

    total_customers = coh.Customers.sum()

    S["repeat_rate_overall_pct"] = (
        round(
            float(
                coh.Repeat_Customers.sum()
                / total_customers
                * 100
            ),
            1,
        )
        if total_customers
        else 0.0
    )

    S["anomaly_days"] = an.Flag.value_counts().to_dict()

    duplicate_checks = dq[
        dq.Check.str.startswith("Possible duplicate")
    ]

    S["possible_dup_lines"] = (
        int(duplicate_checks.Result.iloc[0])
        if not duplicate_checks.empty
        else 0
    )

    # Export reports.
    reports = {
        "dq_report": dq,
        "monthly_net_sales": daily,
        "product_ranking_top50": prod.head(50),
        "cohorts": coh,
        "regional": reg,
        "clv_summary": clv_s,
        "anomalies": (
            an[an.Flag.str.startswith("ANOMALY")]
            .reset_index()
        ),
        "exceptions_summary": (
            res.exceptions
            .groupby(["Severity", "Flag"])
            .size()
            .rename("Rows")
            .reset_index()
        ),
        "review_sample": res.review.head(500)[
            [
                "Raw_Row_ID",
                "Order_ID",
                "SKU",
                "Qty",
                "Unit_Price",
                "Review_Reasons",
            ]
        ],
    }

    for name, df in reports.items():
        # Preserve the original special handling for DQ report
        # object columns.
        if name == "dq_report":
            df = df.astype({
                c: str
                for c in df.columns
                if df[c].dtype == object
            })

        path = os.path.join(
            out,
            f"retailII_{name}.csv",
        )

        df.to_csv(path, index=False)

    return S, res, dq


def run_olist(d, out):
    os.makedirs(out, exist_ok=True)

    S = {
        "dataset": (
            "Olist Brazilian E-Commerce "
            "(Kaggle olistbr/brazilian-ecommerce)"
        )
    }

    # Load and adapt the source dataset.
    t = time.time()
    fr, ref = A.olist_frames(d)
    S["adapter_s"] = round(time.time() - t, 1)

    raw = fr["orders"]

    S["order_item_lines"] = int(len(raw))
    S["orders"] = int(raw["Order ID"].nunique())

    # Run the main pipeline.
    t = time.time()

    res = rp.run_pipeline(
        raw,
        ref=ref,
        chunks=4,
        audit="capped",
        audit_cap=2000,
        slim=True,
        aggregate_assumption_flags=True,
    )

    elapsed = time.time() - t

    S["pipeline_s"] = round(elapsed, 1)
    S["rows_per_s"] = (
        int(len(raw) / elapsed) if elapsed > 0 else 0
    )
    S["peak_mem_mb"] = round(mem_mb(), 1)

    std = res.standardized

    S["disposition"] = (
        std.Disposition.astype(str)
        .value_counts()
        .to_dict()
    )

    S["ts_status"] = (
        std.TS_Status.astype(str)
        .value_counts()
        .to_dict()
    )

    S["top_flags"] = (
        res.exceptions
        .groupby(["Severity", "Flag"])
        .size()
        .sort_values(ascending=False)
        .head(10)
        .to_dict()
        .__repr__()
    )

    S["revenue_class"] = (
        std[std.Is_Authoritative]
        .Revenue_Class.astype(str)
        .value_counts()
        .to_dict()
    )

    # Payment processing and reconciliation.
    pay, pex = rp.clean_payments(
        fr["payments"],
        std,
        ref,
    )

    S["payments"] = int(len(pay))
    S["payment_flags"] = pex.Flag.value_counts().to_dict()

    S["payment_methods"] = (
        pay.Method.fillna("UNMAPPED")
        .value_counts()
        .to_dict()
    )

    rec = rp.reconcile_payments(
        pay,
        std,
        components=("Net_Minor", "Shipping_Minor"),
    )

    S["payment_recon"] = (
        rec.Recon_Status.value_counts().to_dict()
    )

    # Shipment processing.
    ship, sex = rp.clean_shipments(
        fr["shipments"],
        std,
        ref,
    )

    S["shipments"] = int(len(ship))
    S["shipment_eligible"] = int(
        ship.Metrics_Eligible.sum()
    )
    S["shipment_flags"] = sex.Flag.value_counts().to_dict()

    perf = rp.fulfilment_performance(
        ship,
        by="Carrier",
    )

    S["fulfilment"] = perf.to_dict("records")

    # Reconcile order events.
    ev = fr["events"].copy()

    u = {
        v: rp.parse_timestamp(
            v,
            None,
            ref.source_tz,
        )
        for v in ev.Raw_TS.unique()
    }

    ev["Event_TS"] = ev.Raw_TS.map(
        lambda v: rp.fmt_utc(u[v]["utc"])
    )

    ev = ev.rename(
        columns={"Order ID": "Order_ID"}
    )

    e, st = rp.reconcile_events(
        ev[["Order_ID", "Event_Type", "Event_TS"]]
    )

    S["event_flags"] = {
        k: int(e.Flags.str.contains(k).sum())
        for k in [
            "EVENT_BEFORE_PREDECESSOR",
            "EVENT_TS_MISSING",
            "DUPLICATE_EVENT_TYPE",
        ]
    }

    S["orders_with_contradictory_timestamps"] = int(
        st.Has_Contradiction.sum()
    )

    # Empty returns table: Olist source does not provide the
    # same return-note structure as Online Retail II.
    ret_empty = pd.DataFrame(
        columns=[
            "Return_ID",
            "Order_ID",
            "SKU",
            "Return_Qty",
            "Reason_Code",
            "Refund_Minor",
            "Refund",
            "Currency",
            "Supplier",
            "Link_Status",
        ]
    )

    # Data quality report.
    dq = rp.dq_report(
        raw,
        res,
        None,
        None,
        ref,
        rec,
    )

    S["dq_fail"] = int((dq.Status == "FAIL").sum())
    S["dq_warn"] = int((dq.Status == "WARN").sum())
    S["dq_pass"] = int((dq.Status == "PASS").sum())

    # Analytics.
    f = res.fulfilled

    coh, ret_m = rp.cohort_analysis(f)
    reg = rp.regional_summary(f, ("State",))
    pr = rp.payment_rates(pay)

    S["net_sales_brl_total"] = round(
        float(f.Net_Minor.sum()) / 100,
        2,
    )

    total_customers = coh.Customers.sum()

    S["repeat_rate_overall_pct"] = (
        round(
            float(
                coh.Repeat_Customers.sum()
                / total_customers
                * 100
            ),
            1,
        )
        if total_customers
        else 0.0
    )

    S["customers_with_orders"] = int(
        coh.Customers.sum()
    )

    S["payment_rates_note"] = (
        "no payment status in source -> rates not computed"
        if pr.empty
        else "computed"
    )

    an = rp.daily_metric_anomalies(
        f,
        window=28,
    )

    S["anomaly_days"] = an.Flag.value_counts().to_dict()

    # Export reports.
    reports = {
        "dq_report": dq.astype({"Result": str}),
        "monthly_net_sales": rp.daily_net_sales(f, "M"),
        "product_category_ranking": (
            rp.product_ranking(f).head(50)
        ),
        "cohorts": coh,
        "regional_state": reg,
        "fulfilment_by_carrier": perf,
        "payment_recon_summary": (
            rec.Recon_Status.value_counts()
            .rename("Orders")
            .reset_index()
        ),
        "exceptions_summary": (
            res.exceptions
            .groupby(["Severity", "Flag"])
            .size()
            .rename("Rows")
            .reset_index()
        ),
        "anomalies": (
            an[an.Flag.str.startswith("ANOMALY")]
            .reset_index()
        ),
        "payment_mismatch_sample": (
            rec[
                rec.Recon_Status.isin(
                    ["PAID_LESS", "PAID_MORE"]
                )
            ].head(200)
        ),
    }

    for name, df in reports.items():
        path = os.path.join(
            out,
            f"olist_{name}.csv",
        )

        df.to_csv(path, index=False)

    return S, res, dq


if __name__ == "__main__":
    ap = argparse.ArgumentParser()

    ap.add_argument("--olist")
    ap.add_argument("--retail2")
    ap.add_argument(
        "--out",
        default="real_data_results",
    )

    a = ap.parse_args()

    summ = {}

    if a.retail2:
        summ["online_retail_ii"] = run_online_retail(
            a.retail2,
            a.out,
        )[0]

    if a.olist:
        summ["olist"] = run_olist(
            a.olist,
            a.out,
        )[0]

    os.makedirs(a.out, exist_ok=True)

    summary_path = os.path.join(
        a.out,
        "summary.json",
    )

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(
            summ,
            f,
            indent=2,
            default=str,
        )

    print(
        json.dumps(
            summ,
            indent=2,
            default=str,
        )
    )
