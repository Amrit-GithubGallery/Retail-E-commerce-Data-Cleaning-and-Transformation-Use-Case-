"""Timestamp parsing to UTC: explicit offsets, declared IANA zones (DST-safe), date-order inference."""

import pandas as pd
import re
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, timezone

from .utils import _blank


_TS_ISO = re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})[T ](\d{1,2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?\s*(Z|[+-]\d{2}:?\d{2})?$", re.I)

_TS_DMY = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})[T ](\d{1,2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?\s*(Z|[+-]\d{2}:?\d{2})?$", re.I)

_ZI = {}

def _offset_minutes(tok):
    if tok.upper() == "Z": return 0
    sign = -1 if tok[0] == "-" else 1
    d = tok[1:].replace(":", "")
    return sign * (int(d[:2]) * 60 + int(d[2:]))

_TS_CACHE = {}

def _parse_ts(s, off, tzname, order):
    m = _TS_ISO.match(s); amb = False
    if m:
        g = m.groups(); yy, mm, dd = int(g[0]), int(g[1]), int(g[2])
    else:
        m = _TS_DMY.match(s)
        if not m: return None, "INVALID"
        g = m.groups(); a, b, yy = int(g[0]), int(g[1]), int(g[2])
        if order == "DMY": dd, mm = a, b
        elif order == "MDY": mm, dd = a, b
        elif a == b: dd, mm = a, b
        elif a > 12 and b <= 12: dd, mm = a, b                                 # only DMY is calendar-valid
        elif b > 12 and a <= 12: mm, dd = a, b                                 # only MDY is calendar-valid
        elif a > 12 and b > 12: return None, "INVALID"
        else:
            if g[6] is None and tzname is None and off is None: return None, "AMBIGUOUS_NO_TZ"
            return None, "AMBIGUOUS_DATE_ORDER"
        amb = order is not None and a != b and a <= 12 and b <= 12
    hh, mi, ss, tz = int(g[3]), int(g[4]), int(g[5] or 0), g[6]
    try: naive = datetime(yy, mm, dd, hh, mi, ss)                              # calendar validity (e.g. 30 Feb)
    except ValueError: return None, "INVALID"
    if tz:
        try: dt = naive.replace(tzinfo=timezone(timedelta(minutes=_offset_minutes(tz)))).astimezone(timezone.utc)
        except ValueError: return None, "INVALID"
        return dt, "OK_ASSUMED_ORDER" if amb else "OK"
    if tzname:
        z = _ZI.setdefault(tzname, ZoneInfo(tzname))
        a0, a1 = naive.replace(tzinfo=z, fold=0), naive.replace(tzinfo=z, fold=1)
        u0, u1 = a0.astimezone(timezone.utc), a1.astimezone(timezone.utc)
        if u0.astimezone(z).replace(tzinfo=None) != naive: return None, "NONEXISTENT_DST"   # clock skipped this wall time
        if u0 != u1: return None, "AMBIGUOUS_DST"                                           # wall time happened twice
        return u0, "OK_ASSUMED_TZ_ORDER" if amb else "OK_ASSUMED_TZ"
    if off is not None:
        try: dt = naive.replace(tzinfo=timezone(timedelta(minutes=off))).astimezone(timezone.utc)
        except ValueError: return None, "INVALID"
        return dt, "OK_ASSUMED_TZ_ORDER" if amb else "OK_ASSUMED_TZ"
    return None, "AMBIGUOUS_NO_TZ"

def parse_timestamp(raw, assumed_offset_minutes=None, source_tz=None, date_order=None):
    """-> {"utc": aware datetime | None, "status": OK | OK_ASSUMED_TZ | OK_ASSUMED_ORDER | OK_ASSUMED_TZ_ORDER |
           AMBIGUOUS_NO_TZ | AMBIGUOUS_DATE_ORDER | AMBIGUOUS_DST | NONEXISTENT_DST | INVALID | MISSING}"""
    if _blank(raw): return {"utc": None, "status": "MISSING"}
    if assumed_offset_minutes is not None and source_tz: raise ValueError("give source_tz OR assumed_offset_minutes, not both")
    s = raw.strftime("%Y-%m-%d %H:%M:%S") if isinstance(raw, (datetime, pd.Timestamp)) and getattr(raw, "tzinfo", None) is None \
        else raw.isoformat() if isinstance(raw, (datetime, pd.Timestamp)) else str(raw).strip()
    k = (s, assumed_offset_minutes, source_tz, date_order)
    hit = _TS_CACHE.get(k)
    if hit is None:
        if len(_TS_CACHE) > 400_000: _TS_CACHE.clear()
        hit = _TS_CACHE[k] = _parse_ts(s, assumed_offset_minutes, source_tz, date_order)
    return {"utc": hit[0], "status": hit[1]}

def fmt_utc(dt): return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None

def infer_date_order(values, min_evidence=1):
    """Evidence-based date order for a column of `a/b/yyyy` strings. Returns (order | None, evidence).
    'DMY' only if some value has a first part > 12 and none has a second part > 12 (and vice versa). Otherwise None
    (stay quarantined) - the function refuses to guess from ambiguous-only data."""
    s = pd.Series(list(values)).dropna().astype(str).str.strip()
    ex = s.str.extract(r"^(\d{1,2})[-/.](\d{1,2})[-/.]\d{4}\b").dropna()
    if ex.empty: return None, {"dmy_evidence": 0, "mdy_evidence": 0, "ambiguous_rows": 0, "examined": 0}
    ex = ex.astype(int)
    dmy = int(((ex[0] > 12) & (ex[1] <= 12)).sum()); mdy = int(((ex[1] > 12) & (ex[0] <= 12)).sum())
    amb = int(((ex[0] <= 12) & (ex[1] <= 12) & (ex[0] != ex[1])).sum())
    order = "DMY" if dmy >= min_evidence and mdy == 0 else "MDY" if mdy >= min_evidence and dmy == 0 else None
    return order, {"dmy_evidence": dmy, "mdy_evidence": mdy, "ambiguous_rows": amb, "examined": len(ex)}
