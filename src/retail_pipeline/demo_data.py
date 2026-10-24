"""Demo / sample raw data from the brief and a CSV loader."""

import os
import pandas as pd


RAW_COLS = ["Order ID", "Customer ID", "Order TS", "SKU", "Product", "Qty", "Unit Price", "Discount", "Currency", "Status"]

SAMPLE_RAW = pd.DataFrame([
    ["ord-1042", "cust-07",  "2026/05/14 10:30 -04:00",   "mug_blk",  "Blk Ceramic Mug",   2,  "₹ 450.00", "10%",   "INR", "Delivered"],
    ["ORD-1042", "CUST-007", "2026-05-14T14:30:00Z",      "MUG-BLK",  "Black Ceramic Mug", 2,  "450.00",   "45.00", "INR", "delivered"],
    ["ord-1043", "cust-08",  "14-05-2026 09:15",          "TSHIRT-M", "Cotton Tee M",      -1, "799",      "0",     "INR", "Return"],
    ["ORD-1044", "CUST-09",  "2026-05-15T11:00:00+05:30", "BAG-01",   "Canvas Tote",       1,  "$18.00",   "0",     "USD", "Shipped"],
], columns=RAW_COLS)

# ---- Extended, purely illustrative rows (extra optional columns: Channel, Country, Email, Phone, Unit, Line ID, Event Version)
EXT_COLS = RAW_COLS + ["Channel", "Country", "Email", "Phone", "Unit", "Line ID", "Event Version"]

_E = lambda *a: dict(zip(EXT_COLS, a))

EXTENDED_RAW = pd.DataFrame([
    _E("ORD-2001", "cust-10",  "2026-05-16T09:00:00+05:30", "HOODIE-L", "Hoodie L",  1, "₹1,499.00", "5%", "INR", "Delivered", "web", "India", "anita.rao@example.com", "+91 98765 43210", None, None, None),
    _E("ORD-2001", "cust-10",  "2026-05-16T09:00:00+05:30", "BTL-STL",  "Steel Bottle", 2, "650", "0", "INR", "delivered", "Website", "IN", "anita.rao@example.com", "+91 98765 43210", None, None, None),
    _E("ORD-2002", "CUST-011", "2026-05-17 08:00 +05:30",   "MUG_BLK",  "Black Ceramic Mug", 3, "450", "10%", "INR", "Delivered", "Mobile App", "IN", "ravi@example.com", None, None, None, None),
    _E("ORD-2003", "cust-012", "2026-05-17T10:00:00Z",      "TSHIRT-M", "Cotton Tee M", 2, "799", "0", "INR", "Delivered", "web", "in", None, None, None, None, None),
    _E("ORD-2004", "cust-08",  "2026-05-18T12:00:00Z",      "NOTE-A5",  "Spiral Notebook A5", 1, "120", "0", "INR", "Delivered", "app", "India", None, None, "pack", None, None),
    _E("ORD-2005", "cust-09",  "2026-05-18T12:30:00Z",      "MUG-BLK",  "Black Ceramic Mug", 1, "450", "0", "INR", "Cancelled", "web", "IN", None, None, None, None, None),
    _E("ORD-2006", "cust-99",  "2026-05-19T08:00:00Z",      "BAG-01",   "Canvas Tote", 2, "$18.00", "0", "USD", "Delivered", "web", "US", None, None, None, None, None),
    _E("ORD-2007", "cust-10",  "2026-05-19T09:00:00Z",      "XYZ-999",  "Mystery Item", 1, "100", "0", "INR", "Delivered", "web", "IN", None, None, None, None, None),
    _E("ORD-2008", "cust-11",  "2026-05-20T09:00:00Z",      "HOODIE-L", "Hoodie L", 1, "1499", None, "INR", "Delivered", "web", "IN", None, None, None, None, None),
    _E("ORD-2009", "cust-12",  "2026-05-20T09:30:00Z",      "TSHIRT-M", "Cotton Tee M", 1, "799", "0", "INR", "TEST", "web", "IN", None, None, None, None, None),
    _E("ORD-2010", "cust-10",  "2026-05-21T09:00:00Z",      "MUG-BLK",  "Black Ceramic Mug", 1, "450", "0", "INR", "Shipped", "web", "IN", None, None, None, None, 1),    # late-arriving update:
    _E("ORD-2010", "cust-10",  "2026-05-22T09:00:00Z",      "MUG-BLK",  "Black Ceramic Mug", 1, "450", "0", "INR", "Delivered", "web", "IN", None, None, None, None, 2),  # v2 wins
    _E("ORD-2011", "cust-09",  "2026-05-22T10:00:00Z",      "BTL-STL",  "Steel Bottle", 1, "650", "0", "INR", "Delivered", "web", "IN", None, None, None, None, 1),
    _E("ORD-2011", "cust-09",  "2026-05-22T10:00:00Z",      "BTL-STL",  "Steel Bottle", 4, "650", "0", "INR", "Delivered", "web", "IN", None, None, None, None, 1),   # same version, conflicting qty
])

DEMO_RETURNS_RAW = pd.DataFrame([
    ["RET-1", "ORD-2002", "MUG_BLK", 1, "damaged", "405", "INR"],          # valid: 1 of 3 mugs, refund = line net per unit (450 - 10% = 405)
    ["RET-2", "ORD-2003", "TSHIRT-M", 1, "size too small", "799", "INR"],  # valid
    ["RET-3", "ORD-9999", "MUG-BLK", 1, "changed mind", "450", "INR"],     # unknown order -> exception
    ["RET-4", "ORD-2003", "TSHIRT-M", 5, "wrong size", "799", "INR"],      # more than sold -> exception
    ["RET-1", "ORD-2002", "MUG_BLK", 1, "damaged", "405", "INR"],          # duplicated return id
], columns=["Return ID", "Order ID", "SKU", "Qty", "Reason", "Refund", "Currency"])

ALL_RAW = pd.concat([SAMPLE_RAW, EXTENDED_RAW], ignore_index=True)

def load_orders(path=None, **read_kw):
    """Load raw orders from CSV when `path` exists, else the in-memory demo rows. CSVs are read as strings (no silent type coercion)."""
    if path and os.path.exists(path): return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""], **read_kw)
    return ALL_RAW.copy()
