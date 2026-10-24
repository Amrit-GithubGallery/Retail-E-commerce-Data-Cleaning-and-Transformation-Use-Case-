"""Row-level cleaner: applies every rule to one raw record."""

import numpy as np
import pandas as pd
from decimal import Decimal, ROUND_HALF_UP

from .identifiers import normalize_qty, resolve_customer, resolve_sku
from .labels import normalize_label, normalize_postal, normalize_state, normalize_status
from .money import normalize_currency, parse_discount, parse_money_ex, to_minor
from .privacy import mask_email, mask_phone
from .promotions import evaluate_promo, normalize_promo_code
from .reference import _R
from .timestamps import fmt_utc, parse_timestamp
from .utils import _blank, _key


_NOFLAGS = ()

def _f(d): return float(d) if d is not None else np.nan

def _opt(r, k): v = r.get(k); return None if _blank(v) else v

def clean_row(r, rid, fx_rates=None, assumed_offset_minutes=None, ref=None, date_order=None, audit=True, slim=False):
    ref = _R(ref); fx_rates = fx_rates or {}
    flags, aud = [], []
    def add(code, detail=""): flags.append((code, detail))
    def log(field, before, after, rule):
        if audit and str(before) != str(after):
            aud.append((rid, field, before, after, rule))
    out = {"Raw_Row_ID": rid}

    # --- IDs (Scenario 1, 11)
    oid = ref.order_id_normalizer(r.get("Order ID"))
    if oid is None: add("INVALID_ORDER_ID", f"raw={r.get('Order ID')!r}")
    log("Order_ID", r.get("Order ID"), oid, "R1 trim / case / ID pattern")
    cust, issue = resolve_customer(r.get("Customer ID"), ref)
    if issue: add(issue, f"raw={r.get('Customer ID')!r} (kept NULL, not replaced)")
    log("Customer_ID", r.get("Customer ID"), cust, "R11 resolve to customer master")
    out.update(Order_ID=oid, Customer_ID=cust)

    # --- Timestamp (Scenario 2)
    ts = parse_timestamp(r.get("Order TS"), assumed_offset_minutes, ref.source_tz if assumed_offset_minutes is None else None,
                         date_order or ref.date_order)
    st = ts["status"]
    if st == "OK": pass
    elif st.startswith("OK_"):
        if "TZ" in st: add("TS_TZ_ASSUMED", f"raw={r.get('Order TS')!r}; source tz={ref.source_tz or assumed_offset_minutes}")
        if "ORDER" in st: add("TS_DATE_ORDER_ASSUMED", f"raw={r.get('Order TS')!r}")
    else:
        code = {"AMBIGUOUS_NO_TZ": "TS_AMBIGUOUS_NO_TZ", "AMBIGUOUS_DATE_ORDER": "TS_AMBIGUOUS_DATE_ORDER", "INVALID": "TS_INVALID",
                "MISSING": "TS_MISSING", "AMBIGUOUS_DST": "TS_DST_AMBIGUOUS", "NONEXISTENT_DST": "TS_DST_NONEXISTENT"}[st]
        add(code, f"raw={r.get('Order TS')!r}")
    utc = fmt_utc(ts["utc"])
    log("Order_TS_UTC", r.get("Order TS"), utc, "R2 parse + convert to UTC")
    out.update(Order_TS_UTC=utc, TS_Status=st)

    # --- SKU & catalogue attributes (Scenario 3, 17)
    raw_sku, line_type = r.get("SKU"), "PRODUCT"
    if not _blank(raw_sku) and _key(raw_sku) in ref.non_product:               # postage, fees, manual adjustments ...
        line_type = ref.non_product[_key(raw_sku)]; sku, issue = None, None
        out_sku = str(raw_sku).strip().upper()
    else:
        ck = (raw_sku, r.get("Product")) if not (_blank(raw_sku) and _blank(r.get("Product"))) else None
        if ck is not None and ck in ref._cache: sku, issue = ref._cache[ck]
        else:
            sku, issue = resolve_sku(raw_sku, r.get("Product"), ref)
            if ck is not None and len(ref._cache) < 500_000: ref._cache[ck] = (sku, issue)
        out_sku = sku
    if issue: add(issue, f"raw sku={raw_sku!r}, product={r.get('Product')!r}")
    log("SKU", raw_sku, out_sku, "R3 canonical SKU")
    c = ref.cat.get(sku) if sku else None
    prod = c["Product"] if c else None
    log("Product", r.get("Product"), prod, "R3 product name from catalogue")
    category = c["Category"] if c is not None and not pd.isna(c["Category"]) else None
    supplier = c["Supplier"] if c is not None and not pd.isna(c["Supplier"]) else None
    if supplier is None and not _blank(r.get("Supplier")): supplier = str(r.get("Supplier")).strip()
    out.update(SKU=out_sku, Product=prod, Category=category,
               Brand=c["Brand"] if c is not None and not pd.isna(c["Brand"]) else None, Supplier=supplier, Line_Type=line_type)

    # --- Quantity (Scenario 4, 9)
    q_sold, q_base, factor, issue = normalize_qty(r.get("Qty"), r.get("Unit"), sku, ref)
    if issue: add(issue, f"raw qty={r.get('Qty')!r}, unit={r.get('Unit')!r}")
    if q_base is not None:
        if q_base <= 0: add("INVALID_QTY", f"qty={q_base} (<= 0): not treated as a sale")
        elif q_base > ref.qty_max: add("QTY_OUT_OF_RANGE", f"qty={q_base} > {ref.qty_max}")
    log("Qty", r.get("Qty"), q_base, "R4 base-unit quantity")

    # --- Price (Scenario 5, 9)
    price, exact, hint, issue = parse_money_ex(r.get("Unit Price"))
    if issue: add("INVALID_PRICE", f"{issue}: raw={r.get('Unit Price')!r}")
    elif price <= 0: add("INVALID_PRICE", f"price={price} (<= 0)")
    elif price > ref.price_max: add("PRICE_OUT_OF_RANGE", f"price={price}")
    elif exact != price: add("PRICE_ROUNDED", f"raw={exact} rounded to {price} (2dp currency precision)")
    price_ok = price is not None and Decimal(0) < price <= ref.price_max

    # --- Discount (Scenario 5, 9, 19)
    basis = "RECORDED"
    if ref.discount_policy == "ABSENT_IN_SOURCE" and _blank(r.get("Discount")):
        disc, issue, basis = Decimal("0.00"), None, "NOT_RECORDED_IN_SOURCE"   # source has no discount field at all (declared policy)
    else:
        disc, issue = parse_discount(r.get("Discount"), price)
        if issue == "DISCOUNT_UNKNOWN": basis = "UNKNOWN"
    if issue: add(issue, f"raw={r.get('Discount')!r}")
    if disc is not None and price_ok and (disc < 0 or disc > price):
        add("DISCOUNT_INVALID", f"discount={disc} outside [0, unit price={price}]"); disc = None
    log("Discount", r.get("Discount"), disc, "R5/R6 discount -> absolute per-unit amount")

    # --- Shipping / tax (Scenario 5): optional, per line, never defaulted
    ship_m = tax_m = None
    for col, flag in (("Shipping", "SHIPPING_INVALID"), ("Tax", "TAX_INVALID")):
        v = r.get(col)
        if _blank(v): continue
        val, _, _, iss = parse_money_ex(v)
        if iss or val < 0: add(flag, f"raw={v!r}")
        elif col == "Shipping": ship_m = to_minor(val)
        else: tax_m = to_minor(val)

    # --- Currency (Scenario 6)
    ccy, issue = normalize_currency(r.get("Currency"), hint, ref)
    if issue: add(issue, f"raw currency={r.get('Currency')!r}, symbol hint={hint}")
    log("Currency", r.get("Currency"), ccy, "R6 currency code")

    # --- Status (Scenario 10, 13, 18)
    status, issue = normalize_status(r.get("Status"), ref)
    if issue: add(issue, f"raw={r.get('Status')!r}")
    status = status or "UNKNOWN"
    if status == "RETURN_REVIEW": add("RETURN_ON_ORDER_LINE", "return status on an order line; link via returns table")
    log("Status", r.get("Status"), status, "R10 status vocabulary")
    rev_class = "NON_PRODUCT" if line_type != "PRODUCT" else ref.revenue_class[status]

    # --- Channel / country / state / postal (Scenario 7)
    chan, issue = normalize_label(r.get("Channel"), ref.channel_map, "CHANNEL_UNMAPPED")
    if issue: add(issue, f"raw={r.get('Channel')!r}")
    ctry, issue = normalize_label(r.get("Country"), ref.country_map, "COUNTRY_UNMAPPED")
    if issue: add(issue, f"raw={r.get('Country')!r}")
    state, issue = normalize_state(r.get("State"), ctry)
    if issue: add(issue, f"raw={r.get('State')!r}")
    postal, issue = normalize_postal(r.get("Postal Code"), ctry)
    if issue: add(issue, f"raw={r.get('Postal Code')!r}")

    # --- Line amounts in INTEGER MINOR UNITS from SOLD-unit values (A5)
    sp_m = to_minor(price) if price_ok else None
    sd_m = to_minor(disc) if disc is not None else None
    gross_m = disc_m = net_m = None
    if q_sold is not None and q_sold > 0 and sp_m is not None:
        gross_m = q_sold * sp_m
        if sd_m is not None: disc_m = q_sold * sd_m; net_m = gross_m - disc_m

    # --- Promotion (Scenario 12)
    promo = normalize_promo_code(r.get("Promo Code"))
    pstat, pflag = evaluate_promo(promo, ts["utc"], gross_m, category, ref)
    if pflag: add(pflag, f"code={promo!r}")
    if pstat == "APPLIED" and (disc_m is not None and disc_m == 0): add("PROMO_NO_DISCOUNT", f"code={promo!r} applied but discount is 0")

    # --- FX (Scenario 6): documented dated rate only; exact Decimal arithmetic, half-up to minor units
    rate, net_rep_m = None, None
    if ccy == ref.reporting_currency: rate = Decimal(1)
    elif ccy and utc: rate = fx_rates.get((utc[:10], ccy))
    if rate is not None: rate = Decimal(str(rate))
    if net_m is not None and rate is not None: net_rep_m = int((Decimal(net_m) * rate).to_integral_value(ROUND_HALF_UP))
    if gross_m is not None and ccy and rate is None:
        add("FX_UNAVAILABLE", f"no {ccy}->{ref.reporting_currency} rate for {utc[:10] if utc else 'unknown date'}")

    # --- Event version / line id (Scenario 8)
    try: ev = int(float(r.get("Event Version"))) if not _blank(r.get("Event Version")) else 1
    except (TypeError, ValueError): ev = 1
    lid = r.get("Line ID")
    if isinstance(lid, float) and not pd.isna(lid) and lid.is_integer(): lid = int(lid)
    line_id = str(lid).strip().upper() if not _blank(lid) else (out_sku or "NA")

    out.update(
        Line_ID=line_id, Event_Version=ev, Sold_Qty=q_sold if q_sold is not None and factor else None,
        Qty=q_base, Unit_Price=_f(price / Decimal(factor)) if (price_ok and factor) else np.nan,
        Discount=_f(disc / Decimal(factor)) if (disc is not None and factor) else np.nan,
        Sold_Unit_Price_Minor=sp_m, Sold_Discount_Minor=sd_m, Discount_Basis=basis,
        Currency=ccy, Status=status, Revenue_Class=rev_class, Channel=chan, Country=ctry, State=state, Postal_Code=postal,
        Promo_Code=promo, Promo_Status=pstat,
        Shipping_Minor=ship_m, Tax_Minor=tax_m, Gross_Minor=gross_m, Discount_Total_Minor=disc_m, Net_Minor=net_m,
        FX_Rate=_f(rate), Net_Reporting_Minor=net_rep_m,
        Gross=gross_m / 100 if gross_m is not None else np.nan, Discount_Total=disc_m / 100 if disc_m is not None else np.nan,
        Net=net_m / 100 if net_m is not None else np.nan, Net_Reporting=net_rep_m / 100 if net_rep_m is not None else np.nan,
        Flags=flags if flags else _NOFLAGS)
    if not slim:                                                                 # Scenario 15: raw PII never enters the dataset
        out.update(Raw_Order_TS=r.get("Order TS"), Raw_Status=r.get("Status"),
                   Email_Masked=mask_email(r.get("Email")), Phone_Masked=mask_phone(r.get("Phone")))
    return out, aud
