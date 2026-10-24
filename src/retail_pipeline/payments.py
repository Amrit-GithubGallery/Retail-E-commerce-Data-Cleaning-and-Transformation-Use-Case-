"""Payments cleaning and reconciliation against order totals."""

import numpy as np
import pandas as pd

from .labels import normalize_label
from .money import normalize_currency, parse_money_ex, to_minor
from .reference import _R
from .utils import _blank


PAYMENT_METHOD_MAP = {"card": "CARD", "credit card": "CARD", "credit": "CARD", "debit card": "CARD", "debit": "CARD",
                      "visa": "CARD", "mastercard": "CARD", "wallet": "WALLET", "paytm": "WALLET", "paypal": "WALLET",
                      "gpay": "WALLET", "phonepe": "WALLET", "apple pay": "WALLET", "upi": "UPI",
                      "net banking": "BANK_TRANSFER", "netbanking": "BANK_TRANSFER", "bank transfer": "BANK_TRANSFER",
                      "transfer": "BANK_TRANSFER", "wire": "BANK_TRANSFER", "boleto": "BANK_SLIP",
                      "cod": "CASH", "cash": "CASH", "cash on delivery": "CASH", "voucher": "VOUCHER", "gift card": "VOUCHER"}

PAYMENT_STATUS_MAP = {"captured": "CAPTURED", "paid": "CAPTURED", "success": "CAPTURED", "succeeded": "CAPTURED", "settled": "CAPTURED",
                      "complete": "CAPTURED", "completed": "CAPTURED", "authorized": "AUTHORIZED", "authorised": "AUTHORIZED",
                      "pending": "PENDING", "processing": "PENDING", "failed": "FAILED", "declined": "FAILED", "error": "FAILED",
                      "refunded": "REFUNDED", "voided": "VOIDED", "cancelled": "VOIDED", "canceled": "VOIDED"}

def clean_payments(pay_raw, std, ref=None, method_map=None, status_map=None, repeat_fail_n=3):
    """Scenario 10 (+16): normalise method/status, parse amounts to minor units, link to orders, flag repeated failures.
    Raw columns: Order ID, Method, Amount; optional Payment ID, Status, Currency. A missing Status column -> 'NOT_RECORDED'."""
    ref = _R(ref); mm = {**PAYMENT_METHOD_MAP, **(method_map or {})}; sm = {**PAYMENT_STATUS_MAP, **(status_map or {})}
    auth = std[std.Is_Authoritative]
    order_ccy = auth.groupby("Order_ID", observed=True).Currency.agg(lambda s: s.dropna().iloc[0] if s.notna().any() else None).to_dict()
    out, exc = [], []
    for i, r in enumerate(pay_raw.to_dict("records"), start=1):
        flags = []
        oid = ref.order_id_normalizer(r.get("Order ID"))
        meth, mi = normalize_label(r.get("Method"), mm, "PAYMENT_METHOD_UNMAPPED")
        if mi or meth is None: flags.append(("PAYMENT_METHOD_UNMAPPED", f"raw={r.get('Method')!r}"))
        if _blank(r.get("Status")): stat = "NOT_RECORDED"
        else:
            stat, si = normalize_label(r.get("Status"), sm, "PAYMENT_STATUS_UNKNOWN")
            if si or stat is None: flags.append(("PAYMENT_STATUS_UNKNOWN", f"raw={r.get('Status')!r}")); stat = "UNKNOWN"
        amt, _, hint, ai = parse_money_ex(r.get("Amount")); am = to_minor(amt) if amt is not None else None
        if ai or (am is not None and am < 0): flags.append(("PAYMENT_AMOUNT_INVALID", f"raw={r.get('Amount')!r}")); am = None
        elif am == 0: flags.append(("PAYMENT_ZERO_AMOUNT", "zero-value payment (e.g. fully voucher-covered)"))
        ccy = normalize_currency(r.get("Currency"), hint, ref)[0] if not _blank(r.get("Currency")) else order_ccy.get(oid)
        if oid not in order_ccy: flags.append(("PAYMENT_UNMATCHED_ORDER", f"no order {oid!r}"))
        elif not _blank(r.get("Currency")) and ccy != order_ccy[oid]: flags.append(("PAYMENT_CURRENCY_MISMATCH", f"{ccy} vs order {order_ccy[oid]}"))
        pid = str(r.get("Payment ID")).strip().upper() if not _blank(r.get("Payment ID")) else f"PAY-ROW-{i}"
        blocking = [f for f in flags if f[0] in {"PAYMENT_UNMATCHED_ORDER", "PAYMENT_AMOUNT_INVALID", "PAYMENT_CURRENCY_MISMATCH"}]
        out.append({"Payment_ID": pid, "Order_ID": oid, "Method": meth, "Status": stat, "Amount_Minor": am, "Currency": ccy,
                    "Link_Status": "EXCEPTION" if blocking else "LINKED"})
        exc += [{"Payment_ID": pid, "Order_ID": oid, "Flag": c, "Severity": "BLOCKING" if (c, d) in blocking else "WARNING", "Detail": d} for c, d in flags]
    pay = pd.DataFrame(out)
    if len(pay):
        pay["Amount_Minor"] = pay["Amount_Minor"].astype("Int64")
        nfail = pay[pay.Status == "FAILED"].groupby("Order_ID").size()                  # Scenario 16: repeated failed payments
        for oid, n in nfail[nfail >= repeat_fail_n].items():
            exc.append({"Payment_ID": None, "Order_ID": oid, "Flag": "REPEATED_FAILED_PAYMENTS", "Severity": "WARNING", "Detail": f"{n} failed attempts"})
    return pay, pd.DataFrame(exc, columns=["Payment_ID", "Order_ID", "Flag", "Severity", "Detail"])

def reconcile_payments(pay, std, components=("Net_Minor",), tolerance_minor=0):
    """Per order: payments counted (CAPTURED / NOT_RECORDED) vs sum of order-line components. Exact integer comparison.
    Orders where any component is NULL are reported as NO_ORDER_TOTAL, never guessed."""
    a = std[std.Is_Authoritative & (std.Disposition == "CLEAN")]
    comp = a[list(components)].sum(axis=1, min_count=len(components))
    tot = comp.groupby(a.Order_ID, observed=True).agg(lambda s: s.sum(min_count=1) if s.notna().all() else pd.NA)
    p = pay[pay.Link_Status == "LINKED"]
    paid = p[p.Status.isin(["CAPTURED", "NOT_RECORDED"])].groupby("Order_ID").Amount_Minor.sum()
    r = pd.DataFrame({"Order_Total_Minor": tot}).join(paid.rename("Paid_Minor"), how="left")
    r["Paid_Minor"] = r["Paid_Minor"].fillna(0)
    r["Order_Total_Minor"] = pd.to_numeric(r.Order_Total_Minor, errors="coerce").astype("float64")
    r["Paid_Minor"] = pd.to_numeric(r.Paid_Minor, errors="coerce").astype("float64")
    r["Diff_Minor"] = r.Paid_Minor - r.Order_Total_Minor
    r["Recon_Status"] = np.where(r.Order_Total_Minor.isna(), "NO_ORDER_TOTAL",
                         np.where(r.Diff_Minor.abs() <= tolerance_minor, "MATCH", np.where(r.Diff_Minor < 0, "PAID_LESS", "PAID_MORE")))
    return r.reset_index()
