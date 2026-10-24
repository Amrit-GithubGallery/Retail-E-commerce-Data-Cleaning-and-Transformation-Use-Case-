"""Adapters that map real Kaggle/UCI datasets onto the pipeline's raw schema.
Each adapter returns (raw_frames, RefData) and documents every assumption it makes - none are hidden defaults.

    Olist (Kaggle: olistbr/brazilian-ecommerce)            -> olist_frames(dir)
    Online Retail II (UCI 502 / Kaggle mirrors)            -> online_retail_frames(csv)
"""
import os, re
import numpy as np, pandas as pd
from retail_pipeline import (RefData, order_id_rule, numeric_customer_normalizer, derive_reference, _blank)

# ------------------------------------------------------------------ Olist ----
def olist_frames(d, limit_orders=None):
    """Assumptions (declared, auditable):
      * amounts are Brazilian reais (BRL): the dataset has no currency column
      * timestamps are local Brazilian time (America/Sao_Paulo): the dataset documents no zone -> flagged TS_TZ_ASSUMED
      * the source records NO discounts -> discount_policy=ABSENT_IN_SOURCE (net = gross, documented, not measured)
      * one order_items row = one line of quantity 1; (order_id, order_item_id) is the line key
      * entity for customer analysis is customer_unique_id (customer_id is a per-order key)
    """
    rd = lambda n: pd.read_csv(os.path.join(d, n), dtype=str, keep_default_na=False, na_values=[""])
    orders, cust, items = rd("olist_orders_dataset.csv"), rd("olist_customers_dataset.csv"), rd("olist_order_items_dataset.csv")
    prods, sellers, pay = rd("olist_products_dataset.csv"), rd("olist_sellers_dataset.csv"), rd("olist_order_payments_dataset.csv")
    tr = rd("product_category_name_translation.csv")
    if limit_orders: orders = orders.head(limit_orders); items = items[items.order_id.isin(orders.order_id)]; pay = pay[pay.order_id.isin(orders.order_id)]
    en = dict(zip(tr.product_category_name, tr.product_category_name_english))
    prods["Category"] = prods.product_category_name.map(en).fillna(prods.product_category_name)
    cat = pd.DataFrame({"SKU": prods.product_id, "Product": prods.Category.fillna("(uncategorised)"), "Category": prods.Category})
    ref = RefData(cat, set(cust.customer_unique_id), suppliers=None, customer_normalizer=lambda x: str(x).strip().lower(),
                  order_id_normalizer=order_id_rule(r"[0-9a-f]{32}", "lower"), currencies=("BRL",), reporting_currency="BRL",
                  status_map={"created": "PENDING", "approved": "PENDING", "invoiced": "PENDING", "unavailable": "UNAVAILABLE"},
                  revenue_class={"UNAVAILABLE": "EXCLUDED"}, country_map={"br": "BR"}, source_tz="America/Sao_Paulo",
                  discount_policy="ABSENT_IN_SOURCE", name="olist (catalogue/customers from the dataset's own tables)")
    o = orders.merge(cust[["customer_id", "customer_unique_id", "customer_state"]], on="customer_id", how="left")
    lines = items.merge(o, on="order_id", how="left")
    raw = pd.DataFrame({"Order ID": lines.order_id, "Customer ID": lines.customer_unique_id, "Order TS": lines.order_purchase_timestamp,
                        "SKU": lines.product_id, "Product": None, "Qty": 1, "Unit Price": lines.price, "Currency": "BRL",
                        "Status": lines.order_status, "Line ID": lines.order_item_id, "Shipping": lines.freight_value,
                        "Country": "BR", "State": lines.customer_state, "Supplier": lines.seller_id})
    ship = pd.DataFrame({"Order ID": orders.order_id, "Carrier": None, "Tracking ID": None,
                         "Status": orders.order_status.where(orders.order_status.isin(["delivered", "shipped"])),
                         "Shipped TS": orders.order_delivered_carrier_date, "Delivered TS": orders.order_delivered_customer_date,
                         "Promised TS": orders.order_estimated_delivery_date})
    pays = pd.DataFrame({"Payment ID": pay.order_id + "|" + pay.payment_sequential, "Order ID": pay.order_id, "Method": pay.payment_type,
                         "Amount": pay.payment_value})
    ev = pd.concat([pd.DataFrame({"Order ID": orders.order_id, "Event_Type": t, "Raw_TS": orders[c]})
                    for t, c in [("ORDERED", "order_purchase_timestamp"), ("APPROVED", "order_approved_at"),
                                 ("SHIPPED", "order_delivered_carrier_date"), ("DELIVERED", "order_delivered_customer_date")]]).dropna(subset=["Raw_TS"])
    return dict(orders=raw, shipments=ship, payments=pays, events=ev), ref

# --------------------------------------------------------- Online Retail II ---
NON_PRODUCT = {"POST": "POSTAGE", "DOT": "POSTAGE", "C2": "POSTAGE", "M": "MANUAL", "D": "DISCOUNT_LINE", "BANK CHARGES": "FEE",
               "AMAZONFEE": "FEE", "CRUK": "FEE", "ADJUST": "ADJUSTMENT", "ADJUST2": "ADJUSTMENT", "B": "ADJUSTMENT", "S": "SAMPLE",
               "TEST001": "TEST", "TEST002": "TEST"}

def _country_map(values):
    import pycountry
    m = {}
    for v in values:
        if _blank(v): continue
        k = re.sub(r"[\s_\-]+", " ", str(v).strip().lower())
        try: m[k] = pycountry.countries.lookup(str(v)).alpha_2
        except LookupError: pass
    m.update({"eire": "IE", "rsa": "ZA", "usa": "US", "korea": "KR", "czech republic": "CZ"})
    return m                                      # 'Unspecified', 'European Community', 'Channel Islands', ... stay unmapped on purpose

def online_retail_frames(csv, qty_max=10_000, nrows=None):
    """Assumptions (declared):
      * Price is GBP; InvoiceDate is UK local time (Europe/London, DST-aware) - the dataset documents neither explicitly
      * invoices starting 'C' are credit notes -> returns table; they carry NO reference to the original invoice, so none can be
        linked (a true property of the data, surfaced as RETURN_UNMATCHED_LINE, not hidden)
      * no discount field exists -> discount_policy=ABSENT_IN_SOURCE
      * no line id exists -> Line ID = position within the invoice; exact repeated rows are therefore NOT deduplicated
        (they may be legitimate repeat scans) and are reported by the DQ 'possible duplicate' check instead
      * the catalogue/customer master are DERIVED from the data (no master is published) and labelled so
      * quantity ceiling raised to `qty_max` (wholesale customers legitimately buy thousands of units)
    """
    d = pd.read_csv(csv, dtype=str, keep_default_na=False, na_values=[""], nrows=nrows)
    d["is_credit"] = d.Invoice.str.upper().str.startswith("C")
    sales, credit = d[~d.is_credit].copy(), d[d.is_credit].copy()
    sales["Line"] = sales.groupby("Invoice").cumcount() + 1
    prod_rows = sales[~sales.StockCode.fillna("").str.upper().str.replace(r"[^A-Z0-9]", "", regex=True).isin({re.sub(r"[^A-Z0-9]", "", k) for k in NON_PRODUCT})]
    ref = derive_reference(prod_rows, "StockCode", "Description", "Customer ID", customer_normalizer=numeric_customer_normalizer("CUST-"))
    norm = numeric_customer_normalizer("CUST-")
    customers = {norm(v) for v in sales["Customer ID"].dropna().unique()} - {None}      # every customer seen on any sales line
    ref = RefData(ref.catalogue, customers, customer_normalizer=ref.customer_normalizer, order_id_normalizer=order_id_rule(r"[AC]?\d{6}"),
                  currencies=("GBP",), reporting_currency="GBP", source_tz="Europe/London", discount_policy="ABSENT_IN_SOURCE",
                  non_product=NON_PRODUCT, qty_max=qty_max, status_map={"completed": "COMPLETED"}, revenue_class={"COMPLETED": "FULFILLED"},
                  country_map=_country_map(d.Country.dropna().unique()), derived=True, name="derived from Online Retail II")
    raw = pd.DataFrame({"Order ID": sales.Invoice, "Customer ID": sales["Customer ID"], "Order TS": sales.InvoiceDate, "SKU": sales.StockCode,
                        "Product": sales.Description, "Qty": sales.Quantity, "Unit Price": sales.Price, "Currency": "GBP", "Status": "Completed",
                        "Line ID": sales.Line.astype(str), "Country": sales.Country})
    q = pd.to_numeric(credit.Quantity, errors="coerce").abs(); pr = pd.to_numeric(credit.Price, errors="coerce")
    rets = pd.DataFrame({"Return ID": credit.Invoice + "|" + (credit.groupby("Invoice").cumcount() + 1).astype(str), "Order ID": credit.Invoice,
                         "SKU": credit.StockCode, "Qty": q.astype("Int64"), "Reason": None,
                         "Refund": (q * pr.abs()).round(2).astype(str), "Currency": "GBP"})
    return dict(orders=raw, returns=rets, credit_rows=len(credit)), ref