"""Data-quality report."""

import pandas as pd

from .reference import _R


def dq_report(raw_df, res_, returns_clean_=None, returns_exc_=None, ref=None, payments_recon=None):
    ref = _R(ref); std = res_.standardized; auth = std[std.Is_Authoritative]; rows = []
    def add(dim, check, value, status, detail=""): rows.append({"Dimension": dim, "Check": check, "Result": value, "Status": status, "Detail": detail})
    n = len(auth)
    for col in ["Order_ID", "Customer_ID", "Order_TS_UTC", "SKU", "Qty", "Unit_Price", "Discount", "Currency", "Status"]:
        pct = auth[col].notna().mean() * 100
        add("Completeness", f"{col} populated", f"{pct:.1f}%", "PASS" if pct == 100 else "WARN", f"{int(auth[col].isna().sum())} NULL of {n} authoritative rows")
    nrev = int((auth.Disposition == "REVIEW").sum())
    add("Validity", "Rows with no blocking flag", f"{(n - nrev) / n * 100:.1f}%", "PASS" if nrev == 0 else "WARN", f"{nrev} of {n} rows in review queue")
    for code_, cnt in res_.exceptions[res_.exceptions.Severity == "BLOCKING"].Flag.value_counts().items():
        add("Validity", f"Blocking flag: {code_}", int(cnt), "WARN", "see exceptions table")
    okfmt = auth.Order_TS_UTC.dropna().str.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z").all()
    add("Validity", "Order_TS_UTC format (YYYY-MM-DDTHH:MM:SSZ)", bool(okfmt), "PASS" if okfmt else "FAIL")
    na = int(auth.TS_Status.astype(str).str.startswith("OK_").sum())
    add("Validity", "Timestamps resolved by a declared assumption (source tz / date order)", na, "INFO",
        f"source_tz={ref.source_tz}, date_order={ref.date_order or res_.date_order_decision}; filter TS_Status for these rows")
    add("Validity", "Discount basis", auth.Discount_Basis.astype(str).value_counts().to_dict(), "INFO",
        "NOT_RECORDED_IN_SOURCE = source has no discount field; net = gross is then a documented policy, not a measurement")
    add("Uniqueness", "Duplicate raw lines superseded", len(res_.superseded), "INFO", "kept in `superseded` table with Duplicate_Of")
    add("Uniqueness", "Authoritative Line_Key unique", bool(auth.Line_Key.is_unique), "PASS" if auth.Line_Key.is_unique else "FAIL")
    k = ["Order_ID", "SKU", "Order_TS_UTC", "Qty", "Unit_Price", "Currency"]
    pd_ = int(auth.dropna(subset=["Order_ID", "SKU"]).duplicated(k, keep=False).sum())
    add("Uniqueness", "Possible duplicate lines (identical on order/SKU/time/qty/price, different line id)", pd_, "INFO" if pd_ == 0 else "WARN",
        "not dropped: without a source line id, identical rows may be legitimate repeated scans")
    add("Consistency", "Status within vocabulary", sorted(auth.Status.astype(str).unique()), "PASS" if set(auth.Status.astype(str)) <= set(ref.revenue_class) else "FAIL")
    add("Consistency", "Currency within allowed set", sorted(auth.Currency.dropna().astype(str).unique()), "PASS" if auth.Currency.dropna().astype(str).isin(ref.currencies).all() else "FAIL")
    add("Consistency", "Order ID matches the configured ID rule", int(auth.Order_ID.isna().sum()), "PASS" if auth.Order_ID.notna().all() else "WARN", "NULL = failed the ID rule")
    prod = auth[auth.Line_Type == "PRODUCT"]
    ok = prod.SKU.dropna().isin(ref.cat).all() and (ref.suppliers is None or prod.Supplier.dropna().astype(str).isin(ref.suppliers).all()) \
         and (ref.categories is None or prod.Category.dropna().astype(str).isin(ref.categories).all())
    add("Consistency", "SKU / supplier / category keys exist in reference tables", bool(ok), "PASS" if ok else "FAIL",
        "reference is DERIVED from the data: unknown-key checks cannot fail" if ref.derived else "")
    mc = auth.groupby("Order_ID", observed=True).Currency.nunique().max()
    add("Consistency", "One currency per order", int(mc) if pd.notna(mc) else 0, "PASS" if (pd.isna(mc) or mc <= 1) else "WARN")
    cm = auth.Customer_ID.dropna().isin(ref.customers).all()
    add("Consistency", "Customer IDs resolve to master (non-null)", bool(cm), "PASS" if cm else "FAIL",
        "customer master is DERIVED from the data" if ref.derived else "")
    add("Reconciliation", "Raw rows = authoritative + superseded", f"{res_.n_raw} = {n} + {len(res_.superseded)}", "PASS" if res_.n_raw == n + len(res_.superseded) else "FAIL")
    add("Reconciliation", "Authoritative = clean + review", f"{n} = {len(res_.clean)} + {len(res_.review)}", "PASS" if n == len(res_.clean) + len(res_.review) else "FAIL")
    g_all = std.groupby("Currency", observed=True).Gross_Minor.sum(); g_sup = res_.superseded.groupby("Currency", observed=True).Gross_Minor.sum()
    g_aut = auth.groupby("Currency", observed=True).Gross_Minor.sum()
    okg = ((g_all - g_sup.reindex(g_all.index, fill_value=0)) == g_aut.reindex(g_all.index, fill_value=0)).all()
    add("Reconciliation", "Gross (all rows) - superseded = authoritative gross, by currency (exact integers)", {str(k_): int(v) for k_, v in g_aut.items()}, "PASS" if okg else "FAIL")
    by_cls = int(auth.groupby("Revenue_Class", observed=True).Gross_Minor.sum().sum())
    add("Reconciliation", "Gross by revenue class sums to authoritative gross (minor units)", f"{by_cls} vs {int(auth.Gross_Minor.sum())}", "PASS" if by_cls == int(auth.Gross_Minor.sum()) else "FAIL")
    drift = float((auth.Gross - auth.Gross_Minor / 100).abs().max()) if auth.Gross_Minor.notna().any() else 0.0
    add("Reconciliation", "Display floats agree with minor-unit amounts", f"max |diff| = {drift:.6f}", "PASS" if drift < 0.005 else "FAIL")
    add("Reconciliation", "Audit log entries (raw -> clean -> rule)", len(res_.audit), "INFO", f"capped counts: {res_.audit_counts}" if res_.audit_counts else "")
    if returns_clean_ is not None and len(returns_clean_):
        L = int((returns_clean_.Link_Status == "LINKED").sum()); E = int((returns_clean_.Link_Status == "EXCEPTION").sum())
        add("Reconciliation", "Returns: raw (deduped) = linked + exception", f"{len(returns_clean_)} = {L} + {E}", "PASS" if len(returns_clean_) == L + E else "FAIL")
    if payments_recon is not None and len(payments_recon):
        vc = payments_recon.Recon_Status.value_counts().to_dict()
        m = vc.get("MATCH", 0) / max(1, len(payments_recon) - vc.get("NO_ORDER_TOTAL", 0)) * 100
        add("Reconciliation", "Payments vs order totals (exact minor units)", vc, "PASS" if m == 100 else "WARN", f"{m:.2f}% of orders with a known total match")
    return pd.DataFrame(rows)
