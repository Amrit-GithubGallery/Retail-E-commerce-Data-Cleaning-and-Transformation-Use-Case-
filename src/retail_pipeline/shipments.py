"""Shipment cleaning: carrier, tracking, status, chronology, lead times."""

import numpy as np
import pandas as pd
import re

from .labels import normalize_label
from .reference import _R
from .timestamps import fmt_utc, parse_timestamp
from .utils import _blank


CARRIER_MAP = {"blue dart": "BLUE_DART", "bluedart": "BLUE_DART", "dhl": "DHL", "dhl express": "DHL", "fedex": "FEDEX",
               "federal express": "FEDEX", "ups": "UPS", "delhivery": "DELHIVERY", "dtdc": "DTDC", "india post": "INDIA_POST",
               "speed post": "INDIA_POST", "ecom express": "ECOM_EXPRESS", "xpressbees": "XPRESSBEES", "usps": "USPS"}

# Configurable defaults - verify against each carrier's current format before relying on them.
TRACKING_RULES = {"UPS": r"1Z[A-Z0-9]{16}", "FEDEX": r"\d{12}|\d{15}", "DHL": r"\d{10}", "USPS": r"\d{20,22}", "*": r"[A-Z0-9]{8,30}"}

SHIP_STATUS_MAP = {"delivered": "DELIVERED", "in transit": "IN_TRANSIT", "shipped": "IN_TRANSIT", "dispatched": "IN_TRANSIT",
                   "out for delivery": "OUT_FOR_DELIVERY", "returned": "RETURNED_TO_SENDER", "rto": "RETURNED_TO_SENDER",
                   "failed attempt": "DELIVERY_FAILED", "pending": "LABEL_CREATED", "label created": "LABEL_CREATED"}

def clean_shipments(ship_raw, std, ref=None, carrier_map=None, tracking_rules=None, status_map=None):
    """Scenarios 14 + 20: carrier / tracking / status normalisation, timestamp parsing under the source-zone policy,
    chronology checks (delivered before shipped, shipped before ordered). Lead-time metrics use only `Metrics_Eligible` rows."""
    ref = _R(ref); cm = {**CARRIER_MAP, **(carrier_map or {})}; tr = {**TRACKING_RULES, **(tracking_rules or {})}
    sm = {**SHIP_STATUS_MAP, **(status_map or {})}
    a = std[std.Is_Authoritative]; first = a.sort_values("Raw_Row_ID").drop_duplicates("Order_ID").set_index("Order_ID")
    ots = pd.to_datetime(first.Order_TS_UTC, utc=True, format="%Y-%m-%dT%H:%M:%SZ", errors="coerce").to_dict()
    def ts(v):
        t = parse_timestamp(v, None, ref.source_tz, ref.date_order); return t["utc"], t["status"]
    out, exc = [], []
    for i, r in enumerate(ship_raw.to_dict("records"), start=1):
        flags = []
        oid = ref.order_id_normalizer(r.get("Order ID"))
        if oid not in first.index: flags.append(("SHIPMENT_UNMATCHED_ORDER", f"no order {oid!r}"))
        car = None
        if not _blank(r.get("Carrier")):
            car, ci = normalize_label(r.get("Carrier"), cm, "CARRIER_UNMAPPED")
            if ci: flags.append((ci, f"raw={r.get('Carrier')!r}"))
        trk = None if _blank(r.get("Tracking ID")) else re.sub(r"[\s-]", "", str(r.get("Tracking ID"))).upper()
        trk_ok = None
        if trk is not None:
            trk_ok = bool(re.fullmatch(tr.get(car, tr["*"]), trk))
            if not trk_ok: flags.append(("TRACKING_INVALID", f"raw={r.get('Tracking ID')!r} for carrier {car}"))
        stat = None
        if not _blank(r.get("Status")):
            stat, si = normalize_label(r.get("Status"), sm, "SHIP_STATUS_UNKNOWN")
            if si: flags.append((si, f"raw={r.get('Status')!r}"))
        ship_t, ss = ts(r.get("Shipped TS")) if not _blank(r.get("Shipped TS")) else (None, "ABSENT")
        del_t, ds = ts(r.get("Delivered TS")) if not _blank(r.get("Delivered TS")) else (None, "ABSENT")
        prom_t, ps = ts(r.get("Promised TS")) if not _blank(r.get("Promised TS")) else (None, "ABSENT")
        for nm, s_ in (("SHIPPED", ss), ("DELIVERED", ds), ("PROMISED", ps)):
            if s_ not in ("ABSENT",) and not s_.startswith("OK"): flags.append(("SHIPMENT_TS_NOT_USABLE", f"{nm}: {s_}"))
        if ship_t and del_t and del_t < ship_t: flags.append(("DELIVERED_BEFORE_SHIPPED", f"{del_t} < {ship_t}"))
        o_t = ots.get(oid)
        if ship_t and o_t is not None and pd.notna(o_t) and pd.Timestamp(ship_t) < o_t: flags.append(("SHIPPED_BEFORE_ORDERED", f"{ship_t} < order {o_t}"))
        if stat == "DELIVERED" and del_t is None: flags.append(("DELIVERED_WITHOUT_TIMESTAMP", "status DELIVERED but no delivered timestamp"))
        if stat not in (None, "DELIVERED") and del_t is not None: flags.append(("STATUS_TS_MISMATCH", f"status {stat} but delivered timestamp present"))
        bad = {"SHIPMENT_UNMATCHED_ORDER", "SHIPMENT_TS_NOT_USABLE", "DELIVERED_BEFORE_SHIPPED", "SHIPPED_BEFORE_ORDERED"}
        eligible = not any(f[0] in bad for f in flags)
        lead = (pd.Timestamp(del_t) - pd.Timestamp(ship_t)).total_seconds() / 86400 if (eligible and ship_t and del_t) else np.nan
        e2e = (pd.Timestamp(del_t) - o_t).total_seconds() / 86400 if (eligible and del_t and o_t is not None and pd.notna(o_t)) else np.nan
        ontime = (del_t <= prom_t) if (eligible and del_t and prom_t) else None
        out.append({"Order_ID": oid, "Carrier": car, "Tracking_ID": trk, "Tracking_Valid": trk_ok, "Status": stat,
                    "Shipped_TS_UTC": fmt_utc(ship_t), "Delivered_TS_UTC": fmt_utc(del_t), "Promised_TS_UTC": fmt_utc(prom_t),
                    "Ship_to_Delivery_Days": lead, "Order_to_Delivery_Days": e2e, "On_Time": ontime, "Metrics_Eligible": eligible})
        exc += [{"Order_ID": oid, "Flag": c, "Severity": "BLOCKING" if c in bad else "WARNING", "Detail": d} for c, d in flags]
    return pd.DataFrame(out), pd.DataFrame(exc, columns=["Order_ID", "Flag", "Severity", "Detail"])
