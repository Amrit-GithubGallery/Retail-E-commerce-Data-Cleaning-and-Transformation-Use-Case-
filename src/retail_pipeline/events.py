"""Out-of-order / late-arriving event reconciliation."""

import pandas as pd


LIFECYCLE = {"ORDERED": 1, "APPROVED": 2, "PAID": 3, "SHIPPED": 4, "DELIVERED": 5, "RETURNED": 6}

def reconcile_events(events, lifecycle=None, late_hours=24):
    """events: Order_ID, Event_Type, Event_TS (parseable, UTC), optional Ingested_At.
    -> (events with flags, per-order reconciled state)."""
    lc = lifecycle or LIFECYCLE
    e = events.copy()
    e["Event_TS"] = pd.to_datetime(e["Event_TS"], utc=True, errors="coerce")
    e["Rank"] = e["Event_Type"].map(lc)
    e["Flags"] = ""
    def flag(mask, code): e.loc[mask, "Flags"] = e.loc[mask, "Flags"] + (code + ";")
    flag(e.Rank.isna(), "EVENT_TYPE_UNKNOWN"); flag(e.Event_TS.isna(), "EVENT_TS_MISSING")
    ok = e[e.Rank.notna() & e.Event_TS.notna()].sort_values(["Order_ID", "Rank", "Event_TS"])
    pred = ok.groupby("Order_ID").Event_TS.cummax().groupby(ok.Order_ID).shift(1)
    flag(e.index.isin(ok.index[(ok.Event_TS < pred).values]), "EVENT_BEFORE_PREDECESSOR")
    flag(e.duplicated(["Order_ID", "Event_Type"], keep=False) & e.Rank.notna(), "DUPLICATE_EVENT_TYPE")
    if "Ingested_At" in e:
        e["Ingested_At"] = pd.to_datetime(e["Ingested_At"], utc=True, errors="coerce")
        flag(((e.Ingested_At - e.Event_TS) > pd.Timedelta(hours=late_hours)).fillna(False), "LATE_ARRIVING")
        arr = e[e.Rank.notna() & e.Ingested_At.notna()].sort_values(["Order_ID", "Ingested_At", "Rank"])
        inv = arr.groupby("Order_ID").Rank.cummax().groupby(arr.Order_ID).shift(1) > arr.Rank
        flag(e.index.isin(arr.index[inv.values]), "ARRIVED_OUT_OF_ORDER")
    k = e[e.Rank.notna()]
    final = k.sort_values(["Order_ID", "Rank", "Event_TS"]).groupby("Order_ID").tail(1).set_index("Order_ID")
    state = pd.DataFrame({"Reconciled_Status": final.Event_Type})
    if "Ingested_At" in e:
        last = k.sort_values(["Order_ID", "Ingested_At"]).groupby("Order_ID").tail(1).set_index("Order_ID")
        state["Last_Arrived_Status"] = last.Event_Type
        state["Naive_Would_Be_Wrong"] = state.Reconciled_Status != state.Last_Arrived_Status
    state["Has_Contradiction"] = k.assign(f=k.Flags.str.contains("EVENT_BEFORE_PREDECESSOR")).groupby("Order_ID").f.any()
    return e, state.reset_index()
