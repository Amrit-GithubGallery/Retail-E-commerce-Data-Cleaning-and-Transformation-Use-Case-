"""Small shared helpers (blank detection, key normalisation, label normalisation)."""

import pandas as pd
import re


def _blank(x):
    """True for None / NaN / pd.NA / empty or whitespace-only strings."""
    if x is None: return True
    if isinstance(x, str): return x.strip() == ""
    try: return bool(pd.isna(x))
    except (TypeError, ValueError): return False

def _key(x):
    """Alphanumeric matching key: 'mug_blk' / 'MUG-BLK' / 'Mug Blk' -> 'MUGBLK'."""
    return re.sub(r"[^A-Z0-9]", "", str(x).upper())

def _norm_label(x): return re.sub(r"[\s_\-]+", " ", str(x).strip().lower())
