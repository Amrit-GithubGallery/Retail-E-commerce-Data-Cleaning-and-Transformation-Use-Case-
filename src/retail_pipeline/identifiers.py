"""Order-ID, customer, SKU and quantity normalisation."""

import numpy as np
import pandas as pd
import re
from decimal import Decimal, InvalidOperation

from .reference import UNIT_FACTORS, _R
from .utils import _blank, _key


# ---- Scenario 1 / 11: identifiers -------------------------------------------
def normalize_order_id(raw, ref=None): return _R(ref).order_id_normalizer(raw)

def resolve_customer(raw, ref=None):
    """-> (master_id | None, issue). Unmatched IDs are NOT replaced (Scenarios 11, 19)."""
    ref = _R(ref)
    if _blank(raw): return None, "CUSTOMER_ID_MISSING"
    cand = ref.customer_normalizer(raw)
    return (cand, None) if cand in ref.customers else (None, "CUSTOMER_UNMATCHED")

# ---- Scenario 3: SKU / product -----------------------------------------------
def resolve_sku(raw_sku, raw_product=None, ref=None):
    ref = _R(ref)
    if not _blank(raw_sku) and _key(raw_sku) in ref.sku_keys: return ref.sku_keys[_key(raw_sku)], None
    if not _blank(raw_product) and _key(raw_product) in ref.product_keys:
        return ref.product_keys[_key(raw_product)], "SKU_RESOLVED_VIA_NAME"
    return None, "SKU_UNKNOWN"

# ---- Scenario 4: quantity & units --------------------------------------------
def normalize_qty(raw_qty, raw_unit, sku, ref=None):
    """-> (qty_sold:int|None, qty_base:int|None, factor:int|None, issue)."""
    ref = _R(ref)
    if _blank(raw_qty): return None, None, None, "INVALID_QTY"
    try: q = Decimal(str(raw_qty).strip().replace(",", ""))
    except InvalidOperation: return None, None, None, "INVALID_QTY"
    if not q.is_finite() or q != q.to_integral_value(): return None, None, None, "INVALID_QTY"
    q = int(q)
    unit = "each" if _blank(raw_unit) else re.sub(r"[\s.]+", "", str(raw_unit).lower())
    f = UNIT_FACTORS.get(unit)
    if f is None: return q, None, None, "UNIT_UNKNOWN"
    if f == "PACK":
        ps = ref.cat[sku]["Pack_Size"] if sku in ref.cat else np.nan
        if pd.isna(ps): return q, None, None, "UNIT_UNKNOWN"               # catalogue defines no pack size
        f = int(ps)
    return q, q * f, f, None
