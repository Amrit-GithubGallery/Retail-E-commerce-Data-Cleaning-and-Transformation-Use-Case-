"""Pipeline orchestration: clean -> de-duplicate -> classify."""

import numpy as np
import pandas as pd
import zlib
from collections import defaultdict

from .cleaning import clean_row
from .flags import BLOCKING_FLAGS, severity
from .reference import _R
from .timestamps import infer_date_order


class PipelineResult:
    """Container for all pipeline outputs."""
    def __init__(self, **kw): self.__dict__.update(kw)

_COMPARE = ["Order_TS_UTC", "Qty", "Unit_Price", "Discount", "Currency", "Status"]

_INT_COLS = ["Qty", "Sold_Qty", "Sold_Unit_Price_Minor", "Sold_Discount_Minor", "Shipping_Minor", "Tax_Minor",
             "Gross_Minor", "Discount_Total_Minor", "Net_Minor", "Net_Reporting_Minor"]

_CAT_COLS_DF = ["Currency", "Status", "Revenue_Class", "TS_Status", "Country", "Channel", "State", "Category", "Brand",
                "Supplier", "Line_Type", "Promo_Status", "Discount_Basis"]

ASSUMPTION_FLAGS = {"TS_TZ_ASSUMED", "TS_DATE_ORDER_ASSUMED"}

def _core(raw_df, ids, fx_rates, off, ref, order, audit, audit_cap, audit_counts, slim):
    rows, aud = [], []
    for rid, rec in zip(ids, raw_df.to_dict("records")):
        out, a = clean_row(rec, rid, fx_rates, off, ref, order, audit != "off", slim)
        rows.append(out)
        if a:
            for t in a:
                if audit == "capped":
                    audit_counts[t[1]] += 1
                    if audit_counts[t[1]] > audit_cap: continue
                aud.append(t)
    df = pd.DataFrame(rows)
    for c in _INT_COLS: df[c] = df[c].astype("Int64")

    df["Line_Key"] = [f"{o}|{l}|{s}" if o and s else f"UNKEYED|{rid}" for o, l, s, rid in zip(df.Order_ID, df.Line_ID, df.SKU, df.Raw_Row_ID)]
    df["_ts_rank"] = (df.TS_Status != "OK").astype(int)
    df["_complete"] = df[["Customer_ID", "Order_TS_UTC", "Unit_Price", "Discount", "Currency"]].notna().sum(axis=1)
    df = df.sort_values(["Line_Key", "Event_Version", "_ts_rank", "_complete", "Raw_Row_ID"],
                        ascending=[True, False, True, False, True], kind="mergesort").reset_index(drop=True)
    df["Is_Authoritative"] = ~df.duplicated("Line_Key", keep="first")
    auth = df[df.Is_Authoritative].set_index("Line_Key")
    df["Duplicate_Of"] = np.where(df.Is_Authoritative, None, df.Line_Key.map(auth["Raw_Row_ID"]))

    extra = defaultdict(list)                                                    # same version + different values => conflict
    dups = df[~df.Is_Authoritative]
    if len(dups):
        j = dups[["Line_Key", "Raw_Row_ID", "Event_Version"] + _COMPARE].join(
            auth[["Raw_Row_ID", "Event_Version"] + _COMPARE], on="Line_Key", rsuffix="_a")
        for r in j[["Raw_Row_ID", "Raw_Row_ID_a"]].itertuples(index=False):
            if audit != "off": aud.append((r[0], "ROW", f"row {r[0]}", f"superseded by row {r[1]}", "R8 duplicate order line"))
        same = j[j.Event_Version == j.Event_Version_a]
        if len(same):
            dm = pd.DataFrame({c: (same[c].notna() & same[c + "_a"].notna() & (same[c] != same[c + "_a"]).fillna(False).astype(bool)) for c in _COMPARE})
            for (rid_d, rid_a), hit in zip(same[["Raw_Row_ID", "Raw_Row_ID_a"]].itertuples(index=False), dm.values):
                if hit.any(): extra[rid_a].append(("CONFLICTING_DUPLICATE", f"row {rid_d} has same version but differs on {[c for c, h in zip(_COMPARE, hit) if h]}"))
    if extra: df["Flags"] = [list(f) + extra[rid] if rid in extra else f for f, rid in zip(df.Flags, df.Raw_Row_ID)]

    block = lambda fl: ", ".join(sorted({c for c, _ in fl if c in BLOCKING_FLAGS}))
    warn = lambda fl: ", ".join(sorted({c for c, _ in fl if c not in BLOCKING_FLAGS}))
    df["Review_Reasons"] = [block(f) if f else "" for f in df.Flags]
    df["Warnings"] = [warn(f) if f else "" for f in df.Flags]
    df["Disposition"] = np.where(~df.Is_Authoritative, "SUPERSEDED_DUPLICATE", np.where(df.Review_Reasons != "", "REVIEW", "CLEAN"))
    df = df.drop(columns=["_ts_rank", "_complete"])
    for c in _CAT_COLS_DF + ["Disposition"]: df[c] = df[c].astype("category")
    return df, aud

def run_pipeline(raw_df, fx_rates=None, assumed_offset_minutes=None, ref=None, date_order=None,
                 audit="full", audit_cap=5000, chunks=1, slim=False, aggregate_assumption_flags=False):
    """raw_df -> PipelineResult. Raw_Row_ID = 1-based position in `raw_df`.
    date_order: None | "DMY" | "MDY" | "infer" (evidence-based, see infer_date_order).
    audit: "full" | "capped" (<= audit_cap entries per field, counts kept) | "off"."""
    ref = _R(ref); raw_df = raw_df.reset_index(drop=True)
    decision = None
    if date_order == "infer":
        order, ev = infer_date_order(raw_df["Order TS"]) if "Order TS" in raw_df else (None, {})
        decision = (order, ev); date_order = order
    ids = np.arange(1, len(raw_df) + 1)
    audit_counts = defaultdict(int)
    if chunks > 1:
        oids = raw_df["Order ID"].astype(str)
        uniq = {u: ref.order_id_normalizer(u) for u in oids.unique()}
        part = oids.map(lambda u: zlib.crc32(str(uniq[u]).encode()) % chunks).values
        parts = []; aud_all = []
        for k in range(chunks):
            m = part == k
            if not m.any(): continue
            d, a = _core(raw_df[m], ids[m], fx_rates, assumed_offset_minutes, ref, date_order, audit, audit_cap, audit_counts, slim)
            parts.append(d); aud_all.extend(a)
        df = pd.concat(parts, ignore_index=True); aud = aud_all
        for c in _CAT_COLS_DF + ["Disposition"]: df[c] = df[c].astype("category")
    else:
        df, aud = _core(raw_df, ids, fx_rates, assumed_offset_minutes, ref, date_order, audit, audit_cap, audit_counts, slim)
    df = df.sort_values("Raw_Row_ID").reset_index(drop=True)

    flagged = df[df.Is_Authoritative & (df.Flags.map(len) > 0)]
    exc, agg = [], defaultdict(int)
    for r in flagged.itertuples():
        for c, d in r.Flags:
            if aggregate_assumption_flags and c in ASSUMPTION_FLAGS: agg[c] += 1; continue
            exc.append((r.Raw_Row_ID, r.Order_ID, c, severity(c), d))
    for c, n in agg.items(): exc.append((None, None, c, severity(c), f"dataset-level assumption applied to {n} rows (see TS_Status)"))
    exceptions = pd.DataFrame(exc, columns=["Raw_Row_ID", "Order_ID", "Flag", "Severity", "Detail"])

    return PipelineResult(
        standardized=df,
        clean=df[df.Disposition == "CLEAN"].reset_index(drop=True),
        review=df[df.Disposition == "REVIEW"].reset_index(drop=True),
        superseded=df[df.Disposition == "SUPERSEDED_DUPLICATE"].reset_index(drop=True),
        fulfilled=df[(df.Disposition == "CLEAN") & (df.Revenue_Class == "FULFILLED")].reset_index(drop=True),
        exceptions=exceptions,
        audit=pd.DataFrame(aud, columns=["Raw_Row_ID", "Field", "Raw_Value", "Clean_Value", "Rule"]),
        audit_counts=dict(audit_counts), date_order_decision=decision, ref=ref, n_raw=len(raw_df))
