"""Money parsing, exact integer minor units, discounts and currency normalisation."""

import numpy as np
import pandas as pd
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .config import CENT
from .reference import _R
from .utils import _blank


# ---- Scenario 5: money (exact Decimal -> integer minor units) ------------------
_SYM2CCY = {"₹": "INR", "$": "USD", "€": "EUR", "£": "GBP", "R$": "BRL", "RS": "INR", "RS.": "INR",
            "INR": "INR", "USD": "USD", "EUR": "EUR", "GBP": "GBP", "BRL": "BRL"}

_MONEY_RE = re.compile(r"^(?P<n1>-)?\s*(?P<sym>₹|\$|€|£|R\$|Rs\.?|INR|USD|EUR|GBP|BRL)?\s*(?P<n2>-)?\s*"
                       r"(?P<num>\d[\d,]*(?:\.\d+)?|\.\d+)\s*(?P<code>INR|USD|EUR|GBP|BRL)?$", re.I)

def parse_money_ex(raw):
    """-> (value rounded to 2dp | None, EXACT Decimal | None, currency_hint | None, issue | None)."""
    if _blank(raw): return None, None, None, "AMOUNT_MISSING"
    if isinstance(raw, (int, float, np.integer, np.floating)) and not isinstance(raw, bool):
        ex = Decimal(str(raw))
        if not ex.is_finite(): return None, None, None, "UNPARSEABLE_AMOUNT"
        return ex.quantize(CENT, ROUND_HALF_UP), ex, None, None
    m = _MONEY_RE.match(str(raw).strip())
    if not m: return None, None, None, "UNPARSEABLE_AMOUNT"
    num = m.group("num")
    if "," in num and not re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", num):
        return None, None, None, "UNPARSEABLE_AMOUNT"                        # '1,2,3' or European '1.299,50'
    ex = Decimal(num.replace(",", ""))
    if m.group("n1") or m.group("n2"): ex = -ex
    sym = m.group("sym") or m.group("code")
    return ex.quantize(CENT, ROUND_HALF_UP), ex, (_SYM2CCY.get(sym.upper()) if sym else None), None

def parse_money(raw):
    """-> (Decimal(2dp) | None, currency_hint | None, issue | None). Removes symbols / thousands separators."""
    v, _, h, i = parse_money_ex(raw); return v, h, i

def to_minor(d):
    """Decimal (2dp) -> integer minor units (paise / cents / pence). Exact: no float involved."""
    return None if d is None else int((d * 100).to_integral_value(ROUND_HALF_UP))

def minor_to_decimal(m): return None if m is None or pd.isna(m) else Decimal(int(m)) / 100

def parse_discount(raw, unit_price):
    """-> (absolute per-unit discount | None, issue). '10%' means 10 % of the unit price (A6). Blank stays NULL."""
    if _blank(raw): return None, "DISCOUNT_UNKNOWN"
    s = str(raw).strip()
    if s.endswith("%"):
        try: pct = Decimal(s[:-1].strip())
        except InvalidOperation: return None, "DISCOUNT_INVALID"
        if not pct.is_finite() or pct < 0 or pct > 100: return None, "DISCOUNT_INVALID"
        if unit_price is None: return None, "DISCOUNT_UNKNOWN"
        return (unit_price * pct / Decimal(100)).quantize(CENT, ROUND_HALF_UP), None
    amt, _, issue = parse_money(raw)
    return (None, "DISCOUNT_INVALID") if issue else (amt, None)

# ---- Scenario 6: currency -----------------------------------------------------
def normalize_currency(raw, hint=None, ref=None):
    """-> (code | None, issue | None)."""
    ref = _R(ref); code = None
    if not _blank(raw):
        c = str(raw).strip().upper()
        c = {"RS": "INR", "RS.": "INR", "₹": "INR", "US$": "USD", "$": "USD", "R$": "BRL"}.get(c, c)
        if c not in ref.currencies: return None, "CURRENCY_UNKNOWN"
        code = c
    if code and hint and code != hint: return code, "CURRENCY_SYMBOL_CONFLICT"
    if code: return code, None
    if hint in {"INR", "EUR", "GBP", "BRL"} and hint in ref.currencies:
        return hint, "CURRENCY_INFERRED_FROM_SYMBOL"                          # unambiguous symbols only; '$' is NOT inferred
    return None, "CURRENCY_UNKNOWN"
