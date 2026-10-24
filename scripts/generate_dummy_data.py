#!/usr/bin/env python3
"""
Generate a messy, seeded dummy dataset for the Retail & E-commerce cleaning notebook.

Outputs (in --out, default ./data):
  raw_orders.csv   columns: Order ID, Customer ID, Order TS, SKU, Product, Qty, Unit Price, Discount, Currency,
                            Status, Channel, Country, Email, Phone, Unit, Line ID, Event Version
  raw_returns.csv  columns: Return ID, Order ID, SKU, Qty, Reason, Refund, Currency

Usage:
  python generate_dummy_data.py --orders 500 --seed 42 --dirty 0.25 --out data

--dirty is the probability (0-1) that a field is corrupted in each row; 0 gives a clean dataset.
Then in the notebook:  ALL_RAW = pd.read_csv("data/raw_orders.csv");  RETURNS_RAW = pd.read_csv("data/raw_returns.csv")
"""
import argparse, os, random
from datetime import datetime, timedelta, timezone

import pandas as pd

# (sku, canonical product, price, currency, pack_size)
CATALOGUE = [
    ("MUG-BLK",  "Black Ceramic Mug",  450,  "INR", None),
    ("TSHIRT-M", "Cotton Tee M",       799,  "INR", None),
    ("BAG-01",   "Canvas Tote",        18,   "USD", None),
    ("HOODIE-L", "Hoodie L",           1499, "INR", None),
    ("BTL-STL",  "Steel Bottle",       650,  "INR", None),
    ("NOTE-A5",  "Spiral Notebook A5", 120,  "INR", 3),
]
PRODUCT_VARIANTS = {"MUG-BLK": ["Blk Ceramic Mug", "black ceramic mug"], "TSHIRT-M": ["Cotton Tee  M", "cotton tee m"]}
CUSTOMERS = list(range(7, 13))                    # matches the notebook's customer master CUST-007..CUST-012
CHANNELS = ["web", "Website", "app", "Mobile App", "WEB", "store"]
COUNTRIES = ["IN", "India", "in", "US", "USA", "United States"]
STATUSES = ["Delivered"] * 6 + ["Shipped"] * 2 + ["Cancelled", "TEST", "Pending", "Return"]
REASONS = ["Size too small", "Damaged", "defective", "changed mind", "Not as described", "???"]
IST = timezone(timedelta(hours=5, minutes=30))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orders", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dirty", type=float, default=0.25)
    ap.add_argument("--out", default="data")
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    dirty = lambda: rnd.random() < a.dirty

    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    rows = []

    def fmt_ts(dt, messy):
        if not messy:
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        k = rnd.choice(["offset", "ist", "slash", "dmy_notz", "space_offset", "bad", "blank"])
        if k == "offset": return dt.astimezone(timezone(timedelta(hours=-4))).strftime("%Y-%m-%dT%H:%M:%S-04:00")
        if k == "ist":    return dt.astimezone(IST).strftime("%Y-%m-%dT%H:%M:%S+05:30")
        if k == "slash":  return dt.astimezone(timezone(timedelta(hours=-4))).strftime("%Y/%m/%d %H:%M -04:00")
        if k == "dmy_notz": return dt.strftime("%d-%m-%Y %H:%M")          # no timezone -> ambiguous
        if k == "space_offset": return dt.astimezone(IST).strftime("%Y-%m-%d %H:%M +05:30")
        if k == "bad": return "2026-02-30T10:00:00Z"                     # impossible date
        return ""

    def fmt_id(n, messy):
        s = f"ORD-{n}"
        if not messy: return s
        return rnd.choice([s.lower(), f" {s} ", s.replace("-", "_"), s.replace("-", "")])

    def fmt_cust(n, messy):
        if not messy: return f"CUST-{n:03d}"
        return rnd.choice([f"cust-{n}", f"CUST{n:02d}", f"cust-{n:03d}", f"CUST-{n:03d} ", f"CUST-{rnd.randint(90, 99)}", ""])

    def fmt_price(p, ccy, messy):
        if not messy: return f"{p:.2f}"
        sym = {"INR": "₹", "USD": "$"}[ccy]
        return rnd.choice([f"{sym}{p:,.2f}", f"{sym} {p:.2f}", f"{p:.0f}", f"Rs. {p:,.0f}" if ccy == "INR" else f"{p:.2f}"])

    for n in range(1001, 1001 + a.orders):
        cust = rnd.choice(CUSTOMERS)
        ts = start + timedelta(minutes=rnd.randint(0, 60 * 24 * 45))
        email = f"user{cust}@example.com" if rnd.random() < 0.6 else ""
        phone = f"+91 98{rnd.randint(10000000, 99999999)}" if email and rnd.random() < 0.7 else ""
        status = rnd.choice(STATUSES)
        chan, ctry = rnd.choice(CHANNELS), rnd.choice(COUNTRIES)
        for line in range(rnd.choice([1, 1, 1, 2, 3])):
            sku, prod, price, ccy, pack = rnd.choice(CATALOGUE)
            qty, unit = rnd.choice([1, 1, 2, 2, 3, 5]), ""
            if dirty():
                k = rnd.choice(["neg", "zero", "dozen", "pack", "huge"])
                if k == "neg": qty = -rnd.randint(1, 2)
                elif k == "zero": qty = 0
                elif k == "dozen": unit = "dozen"
                elif k == "pack" and pack: unit = "pack"
                elif k == "huge": qty = 5000
            pct = rnd.choice([0, 0, 5, 10, 15, 20])
            disc = f"{pct}%" if (pct and rnd.random() < 0.5) else f"{price * pct / 100:.2f}"
            if dirty() and rnd.random() < 0.5: disc = ""                        # unknown discount
            row = {
                "Order ID": fmt_id(n, dirty()), "Customer ID": fmt_cust(cust, dirty()),
                "Order TS": fmt_ts(ts, dirty()),
                "SKU": (sku.lower().replace("-", "_") if dirty() else sku) if rnd.random() > 0.03 else "XYZ-999",
                "Product": rnd.choice(PRODUCT_VARIANTS.get(sku, [prod])) if dirty() else prod,
                "Qty": qty, "Unit Price": fmt_price(price, ccy, dirty()), "Discount": disc,
                "Currency": ccy if not dirty() else rnd.choice([ccy, ccy.lower(), "", "Rs" if ccy == "INR" else ccy]),
                "Status": status if not dirty() else rnd.choice([status.lower(), status.upper(), status, "canceled", "weird"]),
                "Channel": chan, "Country": ctry, "Email": email, "Phone": phone,
                "Unit": unit, "Line ID": f"L{line + 1}", "Event Version": 1,
            }
            rows.append(row)

            # --- duplicates / late-arriving updates / conflicts
            r = rnd.random()
            if r < 0.06:                                                      # same event, different timestamp notation
                d = dict(row); d["Order TS"] = fmt_ts(ts, True) if row["Order TS"] and "Z" in row["Order TS"] else d["Order TS"]
                rows.append(d)
            elif r < 0.10:                                                    # event v2 supersedes v1
                d = dict(row); d["Event Version"] = 2; d["Status"] = "Delivered"; rows.append(d)
            elif r < 0.12:                                                    # same version, conflicting qty
                d = dict(row); d["Qty"] = (qty if isinstance(qty, int) else 1) + 1; rows.append(d)

    orders = pd.DataFrame(rows)
    orders = orders.sample(frac=1, random_state=a.seed).reset_index(drop=True)      # shuffle (out-of-order arrival)

    # ---- returns: mostly valid, some unmatched / over-quantity / over-refund
    clean = [r for r in rows if r["Status"] == "Delivered" and str(r["Qty"]).lstrip("-").isdigit() and int(r["Qty"]) > 0]
    rets = []
    for i, r in enumerate(rnd.sample(clean, min(len(clean), max(1, a.orders // 12))), start=1):
        price = float(str(r["Unit Price"]).replace("₹", "").replace("$", "").replace("Rs.", "").replace(",", "").strip() or 0)
        q = int(r["Qty"])
        k = rnd.random()
        oid = r["Order ID"]
        if k < 0.15: oid = "ORD-9999"                                          # unknown order line
        rq = q + 1 if 0.15 <= k < 0.25 else rnd.randint(1, q)                  # returned more than sold
        refund = price * rq * (2 if 0.25 <= k < 0.32 else 1)                   # refund exceeds line
        rets.append({"Return ID": f"RET-{i}", "Order ID": oid, "SKU": r["SKU"], "Qty": rq,
                     "Reason": rnd.choice(REASONS), "Refund": f"{refund:.2f}", "Currency": r["Currency"] or "INR"})
    if rets: rets.append(dict(rets[0]))                                        # duplicate return event
    returns = pd.DataFrame(rets)

    os.makedirs(a.out, exist_ok=True)
    orders.to_csv(os.path.join(a.out, "raw_orders.csv"), index=False)
    returns.to_csv(os.path.join(a.out, "raw_returns.csv"), index=False)
    print(f"raw_orders.csv  : {len(orders)} rows  ->  {a.out}/raw_orders.csv")
    print(f"raw_returns.csv : {len(returns)} rows ->  {a.out}/raw_returns.csv")


if __name__ == "__main__":
    main()