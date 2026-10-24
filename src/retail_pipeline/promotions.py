"""Promotion-code normalisation and evaluation."""

import pandas as pd
import re

from .utils import _blank


# ---- Scenario 12: promotions -----------------------------------------------------
def normalize_promo_code(raw):
    return None if _blank(raw) else re.sub(r"[^A-Z0-9]", "", str(raw).upper()) or None

def evaluate_promo(code, ts_utc, gross_minor, category, ref):
    """-> (status, flag|None). NONE / APPLIED / EXPIRED / REJECTED / UNKNOWN_CODE / UNVERIFIABLE (no usable timestamp)."""
    if code is None: return "NONE", None
    p = ref.promotions.get(code)
    if p is None: return "UNKNOWN_CODE", "PROMO_UNKNOWN_CODE"
    if ts_utc is None: return "UNVERIFIABLE", "PROMO_UNVERIFIABLE"
    t = pd.Timestamp(ts_utc)
    if (pd.notna(p["valid_from"]) and t < p["valid_from"]) or (pd.notna(p["valid_to"]) and t > p["valid_to"]):
        return "EXPIRED", "PROMO_EXPIRED"
    if pd.notna(p["min_gross_minor"]) and (gross_minor is None or gross_minor < p["min_gross_minor"]): return "REJECTED", "PROMO_REJECTED"
    if pd.notna(p["eligible_category"]) and category != p["eligible_category"]: return "REJECTED", "PROMO_REJECTED"
    return "APPLIED", None
