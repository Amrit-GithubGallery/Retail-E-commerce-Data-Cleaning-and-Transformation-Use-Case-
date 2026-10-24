"""FX-rate loading/validation and coverage reporting."""

import pandas as pd
from decimal import Decimal

from .reference import _R


def load_fx_rates(path):
    """CSV columns: date (YYYY-MM-DD, the order's UTC calendar date), currency, rate (units of reporting currency per 1 unit).
    Validates positivity, ISO dates and duplicates; returns {(date, currency): Decimal(rate)}."""
    d = pd.read_csv(path, dtype=str)
    d["date"] = pd.to_datetime(d["date"], format="%Y-%m-%d").dt.strftime("%Y-%m-%d")
    d["currency"] = d["currency"].str.strip().str.upper()
    d["rate"] = d["rate"].map(Decimal)
    if (d.rate <= 0).any(): raise ValueError("FX rates must be positive")
    if d.duplicated(["date", "currency"]).any(): raise ValueError("duplicate (date, currency) FX rates")
    return {(r.date, r.currency): r.rate for r in d.itertuples()}

def fx_coverage(res_, fx_rates, ref=None):
    """(date, currency) pairs present in the data that have no FX rate -> explicit, auditable gap list."""
    ref = _R(ref); s = res_.standardized[res_.standardized.Is_Authoritative]
    s = s[s.Currency.notna() & (s.Currency != ref.reporting_currency) & s.Order_TS_UTC.notna()]
    need = set(zip(s.Order_TS_UTC.str[:10], s.Currency)); have = set((fx_rates or {}).keys())
    return pd.DataFrame(sorted(need - have), columns=["Date", "Currency"])
