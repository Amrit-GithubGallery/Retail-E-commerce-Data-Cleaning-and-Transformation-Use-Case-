"""PII masking and fail-closed tokenisation."""

import hashlib
import hmac
import os
import re
import secrets
import warnings

from .utils import _blank


# ---- Scenario 15: privacy ---------------------------------------------------------
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

class MissingTokenKeyError(RuntimeError): pass

_EPHEMERAL_KEY = []

def resolve_token_key(key=None):
    """Fail closed. Order: explicit `key` -> env PII_TOKEN_KEY (>= 16 chars). With neither, raise - unless the caller
    opts in via env PII_ALLOW_EPHEMERAL_KEY=1, which uses a random per-process key (tokens then do NOT join across runs)."""
    k = key or os.environ.get("PII_TOKEN_KEY")
    if k:
        if len(k) < 16: raise MissingTokenKeyError("token key must be at least 16 characters")
        return k.encode()
    if os.environ.get("PII_ALLOW_EPHEMERAL_KEY") == "1":
        if not _EPHEMERAL_KEY: _EPHEMERAL_KEY.append(secrets.token_hex(32))
        warnings.warn("using an EPHEMERAL token key: tokens are not joinable across runs", stacklevel=2)
        return _EPHEMERAL_KEY[0].encode()
    raise MissingTokenKeyError("no PII token key: set PII_TOKEN_KEY (>=16 chars), pass key=..., or opt in to a random key "
                               "with PII_ALLOW_EPHEMERAL_KEY=1")

def mask_email(raw):
    if _blank(raw): return None
    s = str(raw).strip()
    if not _EMAIL_RE.match(s): return "***INVALID_EMAIL***"
    local, domain = s.split("@", 1)
    return f"{local[0]}***@{domain.lower()}"

def mask_phone(raw):
    if _blank(raw): return None
    d = re.sub(r"\D", "", str(raw))
    return "***" if len(d) < 6 else "*" * (len(d) - 2) + d[-2:]

def tokenize(raw, prefix="tok", key=None):
    """Deterministic keyed-hash token (HMAC-SHA256): joinable across extracts, not reversible without the key."""
    if _blank(raw): return None
    return f"{prefix}_" + hmac.new(resolve_token_key(key), str(raw).strip().lower().encode(), hashlib.sha256).hexdigest()[:12]

def analyst_extract(std, key=None, tokenize_email=False):
    """Privacy-safe extract (Scenario 15): customer IDs tokenised with a REQUIRED secret, internal columns dropped.
    Raw email/phone never exist in `std`; only masked values. Raises MissingTokenKeyError if no key is available."""
    resolve_token_key(key)                                                     # fail before doing any work
    out = std.copy()
    cache = {}
    def tok(x):
        if x not in cache: cache[x] = tokenize(x, "cus", key)
        return cache[x]
    out["Customer_Token"] = out["Customer_ID"].map(lambda x: None if _blank(x) else tok(x))
    out["Flags"] = out["Flags"].map(lambda fl: "; ".join(sorted({c for c, _ in fl})))
    return out.drop(columns=[c for c in ["Customer_ID", "Raw_Order_TS", "Raw_Status"] if c in out.columns])
