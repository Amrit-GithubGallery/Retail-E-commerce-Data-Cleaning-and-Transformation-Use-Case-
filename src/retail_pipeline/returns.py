"""Returns cleaning and linkage to order lines."""

import numpy as np
import pandas as pd
from collections import defaultdict

from .identifiers import resolve_sku
from .labels import normalize_label
from .money import normalize_currency, parse_money_ex, to_minor
from .reference import REASON_MAP, _R
from .utils import _blank


def _linkable_lines(std):
    return std[std.Is_Authoritative & (std.Disposition == "CLEAN") & (std.Revenue_Class == "FULFILLED")]

def clean_returns(ret_raw, std, ref=None, reason_map=None):
    """Standardise returns and link each to a clean fulfilled order line (Order_ID + SKU). Exact minor-unit comparisons;
    returned quantity and refunds are checked cumulatively so repeated returns cannot exceed what was sold."""
    ref = _R(ref); reason_map = reason_map or REASON_MAP
    lines = _linkable_lines(std)
    agg = lines.groupby(["Order_ID", "SKU"], observed=True).agg(
        Qty=("Qty", "sum"), Net_Minor=("Net_Minor", lambda s: s.sum(min_count=1)), Currency=("Currency", "first")).to_dict("index")
    out, exc, seen, cum_q, cum_r = [], [], set(), defaultdict(int), defaultdict(int)
    for i, r in enumerate(ret_raw.to_dict("records"), start=1):
        rid = str(r.get("Return ID")).strip().upper()
        if rid in seen:
            exc.append({"Return_ID": rid, "Flag": "RETURN_DUPLICATE_ID", "Severity": "WARNING", "Detail": f"raw row {i} dropped"}); continue
        seen.add(rid)
        oid = ref.order_id_normalizer(r.get("Order ID"))
        sku, _ = resolve_sku(r.get("SKU"), None, ref)
        refund, _, _, ri = parse_money_ex(r.get("Refund")); ref_m = to_minor(refund) if refund is not None else None
        ccy, _ = normalize_currency(r.get("Currency"), None, ref)
        reason, ri2 = normalize_label(r.get("Reason"), reason_map, "RETURN_REASON_UNMAPPED")
        qty = int(r.get("Qty")) if not _blank(r.get("Qty")) else None
        flags = []
        if ri or (ref_m is not None and ref_m < 0): flags.append(("RETURN_REFUND_INVALID", ri or "negative refund"))
        if ri2 or reason is None: flags.append(("RETURN_REASON_UNMAPPED", f"raw={r.get('Reason')!r}"))
        key = (oid, sku); line = agg.get(key)
        if line is not None:
            if qty is None or qty <= 0 or cum_q[key] + qty > line["Qty"]:
                flags.append(("RETURN_QTY_EXCEEDS_SOLD", f"returned={qty} (+{cum_q[key]} already linked), sold={line['Qty']}"))
            if ref_m is not None and pd.notna(line["Net_Minor"]) and cum_r[key] + ref_m > int(line["Net_Minor"]):
                flags.append(("REFUND_EXCEEDS_LINE", f"refund={ref_m/100:.2f} (+{cum_r[key]/100:.2f} already linked), line net={int(line['Net_Minor'])/100:.2f}"))
            if ccy != line["Currency"]: flags.append(("RETURN_CURRENCY_MISMATCH", f"{ccy} vs {line['Currency']}"))
        else:
            flags.append(("RETURN_UNMATCHED_LINE", f"no clean fulfilled line for {oid}/{sku}"))
        blocking = [f for f in flags if f[0] != "RETURN_REASON_UNMAPPED"]
        if line is not None and not blocking:
            cum_q[key] += qty; cum_r[key] += ref_m or 0
        c = ref.cat.get(sku) if sku else None
        out.append({"Return_ID": rid, "Order_ID": oid, "SKU": sku, "Return_Qty": qty, "Reason_Code": reason or "UNMAPPED",
                    "Refund_Minor": ref_m, "Refund": ref_m / 100 if ref_m is not None else np.nan, "Currency": ccy,
                    "Supplier": c["Supplier"] if c is not None and not pd.isna(c["Supplier"]) else None,
                    "Link_Status": "EXCEPTION" if blocking else "LINKED"})
        exc += [{"Return_ID": rid, "Flag": c_, "Severity": "BLOCKING" if (c_, d) in blocking else "WARNING", "Detail": d} for c_, d in flags]
    ret = pd.DataFrame(out)
    if len(ret): ret["Refund_Minor"] = ret["Refund_Minor"].astype("Int64")
    return ret, pd.DataFrame(exc, columns=["Return_ID", "Flag", "Severity", "Detail"])
