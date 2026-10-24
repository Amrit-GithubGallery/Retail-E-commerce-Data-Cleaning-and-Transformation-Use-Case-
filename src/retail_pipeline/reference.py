"""Reference data (`RefData`): catalogue, customer master, vocabularies, currencies, ID rules, source time zone."""

import numpy as np
import pandas as pd
import re
from zoneinfo import ZoneInfo
from decimal import Decimal

from .utils import _blank, _key


STATUS_MAP = {"delivered": "DELIVERED", "shipped": "SHIPPED", "in transit": "SHIPPED",
              "cancelled": "CANCELLED", "canceled": "CANCELLED",
              "return": "RETURN_REVIEW", "returned": "RETURN_REVIEW",
              "test": "TEST", "fraud review": "FRAUD_REVIEW",
              "pending": "PENDING", "processing": "PENDING"}

REVENUE_CLASS = {"DELIVERED": "FULFILLED", "SHIPPED": "IN_PIPELINE", "PENDING": "IN_PIPELINE",
                 "CANCELLED": "EXCLUDED", "TEST": "EXCLUDED", "FRAUD_REVIEW": "EXCLUDED",
                 "RETURN_REVIEW": "REVIEW", "UNKNOWN": "REVIEW"}

CHANNEL_MAP = {"web": "WEB", "website": "WEB", "app": "MOBILE_APP", "mobile app": "MOBILE_APP", "store": "STORE"}

COUNTRY_MAP = {"in": "IN", "india": "IN", "us": "US", "usa": "US", "united states": "US"}

UNIT_FACTORS = {"each": 1, "ea": 1, "pc": 1, "pcs": 1, "piece": 1, "unit": 1,
                "dozen": 12, "doz": 12, "dz": 12, "pack": "PACK"}

REASON_MAP = {"size too small": "WRONG_SIZE", "wrong size": "WRONG_SIZE",
              "damaged": "DAMAGED_DEFECTIVE", "damaged item": "DAMAGED_DEFECTIVE", "defective": "DAMAGED_DEFECTIVE",
              "changed mind": "CHANGE_OF_MIND", "no longer needed": "CHANGE_OF_MIND",
              "not as described": "NOT_AS_DESCRIBED"}

def order_id_rule(pattern, case="upper"):
    """Factory for an order-ID normaliser: strip whitespace, fix case, require a full match of `pattern`."""
    rx = re.compile(pattern)
    def f(raw):
        if _blank(raw): return None
        s = re.sub(r"\s+", "", str(raw))
        s = s.upper() if case == "upper" else s.lower() if case == "lower" else s
        return s if rx.fullmatch(s) else None
    return f

def _default_order_id(raw):
    if _blank(raw): return None
    s = re.sub(r"\s+", "", str(raw)).upper()
    m = re.fullmatch(r"ORD[-_]?(\d+)", s)
    return f"ORD-{m.group(1)}" if m else None

def numeric_customer_normalizer(prefix="CUST-", width=0):
    """'13085', '13085.0' -> 'CUST-13085' (spreadsheet exports often add '.0')."""
    def f(raw):
        s = str(raw).strip()
        if re.fullmatch(r"\d+(\.0+)?", s): return f"{prefix}{int(float(s)):0{width}d}"
        return None
    return f

def _default_customer_normalizer(aliases):
    def f(raw):
        k = _key(raw)
        if k in aliases: return aliases[k]
        m = re.fullmatch(r"CUST0*(\d+)", k)
        return f"CUST-{int(m.group(1)):03d}" if m else None
    return f

_CAT_COLS = ["SKU", "Product", "Category", "Brand", "Supplier", "Base_Unit", "Pack_Size"]

class RefData:
    """All reference data and per-source policies used by the cleaner. Replace placeholders by constructing your own."""
    def __init__(self, catalogue, customers, *, suppliers=None, categories=None, customer_aliases=None,
                 customer_normalizer=None, order_id_normalizer=None, product_aliases=None,
                 currencies=("INR", "USD", "EUR", "GBP"), reporting_currency="INR",
                 status_map=None, revenue_class=None, channel_map=None, country_map=None,
                 source_tz=None, date_order=None, discount_policy="NULL", non_product=None,
                 promotions=None, qty_max=1000, price_max=1_000_000, derived=False, name="custom"):
        cat = catalogue.copy()
        for c in _CAT_COLS:
            if c not in cat.columns: cat[c] = np.nan
        cat["Base_Unit"] = cat["Base_Unit"].fillna("each")
        if not cat.SKU.is_unique: raise ValueError("catalogue SKU is not unique")
        self.name, self.derived = name, derived
        self.catalogue = cat[_CAT_COLS].reset_index(drop=True)
        self.suppliers = set(suppliers) if suppliers is not None else None
        self.categories = set(categories) if categories is not None else None
        if self.suppliers is not None:                                    # Scenario 17: referential integrity
            bad = set(cat.Supplier.dropna()) - self.suppliers
            if bad: raise ValueError(f"catalogue supplier keys not in reference table: {sorted(bad)[:5]}")
        if self.categories is not None:
            bad = set(cat.Category.dropna()) - self.categories
            if bad: raise ValueError(f"catalogue category keys not in reference table: {sorted(bad)[:5]}")
        self.cat = {r["SKU"]: r for r in self.catalogue.to_dict("records")}
        self.sku_keys = {_key(s): s for s in self.catalogue.SKU}
        if len(self.sku_keys) != len(self.catalogue): raise ValueError("SKU keys collide after normalisation")
        self.product_keys = {_key(p): s for p, s in zip(self.catalogue.Product, self.catalogue.SKU) if not _blank(p)}
        self.product_keys.update({_key(k): v for k, v in (product_aliases or {}).items()})
        self.customers = set(customers)
        self.customer_aliases = dict(customer_aliases or {})
        self.customer_normalizer = customer_normalizer or _default_customer_normalizer(self.customer_aliases)
        self.order_id_normalizer = order_id_normalizer or _default_order_id
        self.currencies = set(currencies); self.reporting_currency = reporting_currency
        if reporting_currency not in self.currencies: raise ValueError("reporting currency must be an allowed currency")
        self.status_map = {**STATUS_MAP, **(status_map or {})}
        self.revenue_class = {**REVENUE_CLASS, **(revenue_class or {})}
        for st in set(self.status_map.values()) | {"UNKNOWN"}:
            if st not in self.revenue_class: raise ValueError(f"status {st} has no revenue class")
        self.channel_map = {**CHANNEL_MAP, **(channel_map or {})}
        self.country_map = {**COUNTRY_MAP, **(country_map or {})}
        self.source_tz, self.date_order = source_tz, date_order
        if source_tz: ZoneInfo(source_tz)                                  # fail early on a bad zone name
        if discount_policy not in ("NULL", "ABSENT_IN_SOURCE"): raise ValueError("discount_policy")
        self.discount_policy = discount_policy
        self.non_product = {_key(k): v for k, v in (non_product or {}).items()}
        self.promotions = _prep_promotions(promotions)
        self.qty_max, self.price_max = qty_max, Decimal(price_max)
        self._cache = {}

    @classmethod
    def from_csv(cls, catalogue_csv, customers_csv, customer_col="Customer_ID", **kw):
        """Load masters from CSV files (catalogue needs SKU, Product; optional Category, Brand, Supplier, Base_Unit, Pack_Size)."""
        cat = pd.read_csv(catalogue_csv, dtype={"SKU": str}); cust = pd.read_csv(customers_csv, dtype=str)
        return cls(cat, set(cust[customer_col].dropna()), **kw)

def _prep_promotions(p):
    if p is None: return {}
    d = p.copy()
    d["code"] = d["code"].map(lambda x: re.sub(r"[^A-Z0-9]", "", str(x).upper()))
    for c in ("valid_from", "valid_to"):
        d[c] = pd.to_datetime(d[c], utc=True) if c in d else pd.NaT
    if "min_gross_minor" not in d: d["min_gross_minor"] = np.nan
    if "eligible_category" not in d: d["eligible_category"] = np.nan
    return {r["code"]: r for r in d.to_dict("records")}

def demo_reference():
    cat = pd.DataFrame([
        {"SKU": "MUG-BLK",  "Product": "Black Ceramic Mug",  "Category": "Kitchen",     "Brand": "Hearth",  "Supplier": "SUP-01", "Pack_Size": np.nan},
        {"SKU": "TSHIRT-M", "Product": "Cotton Tee M",       "Category": "Apparel",     "Brand": "Loom",    "Supplier": "SUP-02", "Pack_Size": np.nan},
        {"SKU": "BAG-01",   "Product": "Canvas Tote",        "Category": "Accessories", "Brand": "Carry",   "Supplier": "SUP-03", "Pack_Size": np.nan},
        {"SKU": "HOODIE-L", "Product": "Hoodie L",           "Category": "Apparel",     "Brand": "Loom",    "Supplier": "SUP-02", "Pack_Size": np.nan},
        {"SKU": "BTL-STL",  "Product": "Steel Bottle",       "Category": "Kitchen",     "Brand": "Hearth",  "Supplier": "SUP-01", "Pack_Size": np.nan},
        {"SKU": "NOTE-A5",  "Product": "Spiral Notebook A5", "Category": "Stationery",  "Brand": "Inkwell", "Supplier": "SUP-03", "Pack_Size": 3},
    ])
    return RefData(cat, {f"CUST-{n:03d}" for n in range(7, 13)},
                   suppliers={"SUP-01", "SUP-02", "SUP-03"},
                   categories={"Kitchen", "Apparel", "Accessories", "Stationery"},
                   product_aliases={"blk ceramic mug": "MUG-BLK", "cotton tee m": "TSHIRT-M"},
                   name="demo (illustrative placeholders)")

DEFAULT_REF = demo_reference()

def set_default_reference(ref):
    """Swap the reference used when functions are called without `ref=`."""
    global DEFAULT_REF; DEFAULT_REF = ref

def _R(ref): return ref if ref is not None else DEFAULT_REF

def derive_reference(df, sku_col, name_col, customer_col=None, customer_normalizer=None, **kw):
    """Build a *derived* reference from a dataset that ships no masters: modal product name per SKU, observed customer IDs.
    Derived masters cannot detect unknown SKUs/customers (everything observed is 'known'), so DQ reports mark them derived."""
    d = df[[sku_col, name_col]].dropna(subset=[sku_col]).copy()
    d[sku_col] = d[sku_col].astype(str).str.strip().str.upper()
    d[name_col] = d[name_col].fillna("").astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
    mode = d.groupby(sku_col)[name_col].agg(lambda s: s[s != ""].mode().iloc[0] if (s != "").any() else None)
    cat = pd.DataFrame({"SKU": mode.index, "Product": mode.values})
    norm = customer_normalizer or numeric_customer_normalizer()
    custs = set()
    if customer_col:
        custs = {norm(v) for v in df[customer_col].dropna().unique()} - {None}
    return RefData(cat, custs, customer_normalizer=norm, derived=True, name="derived from data", **kw)
