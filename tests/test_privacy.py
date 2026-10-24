"""Tests: privacy."""
import warnings
from src.retail_pipeline import MissingTokenKeyError, analyst_extract
from .helpers import P, TEST_KEY, case, env, mk


# ---------------- limitation fix 4: token key ----------------
@case("K01", "Fail-closed PII tokens", "no key / short key / explicit key / opt-in ephemeral", "No silent default key; deterministic with a key")
def test_k01():
    r = P(mk()).standardized
    with env(PII_TOKEN_KEY=None, PII_ALLOW_EPHEMERAL_KEY=None):
        try: analyst_extract(r); raise AssertionError("tokenised without a key")
        except MissingTokenKeyError: pass
        try: analyst_extract(r, key="short"); raise AssertionError("short key accepted")
        except MissingTokenKeyError: pass
        a = analyst_extract(r, key=TEST_KEY).Customer_Token.iloc[0]; b = analyst_extract(r, key=TEST_KEY).Customer_Token.iloc[0]
        c = analyst_extract(r, key=TEST_KEY + "x").Customer_Token.iloc[0]; assert a == b and a != c and "CUST-007" not in a
    with env(PII_TOKEN_KEY=None, PII_ALLOW_EPHEMERAL_KEY="1"):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always"); analyst_extract(r); assert any("EPHEMERAL" in str(x.message) for x in w)
    with env(PII_TOKEN_KEY=TEST_KEY): assert analyst_extract(r).Customer_Token.iloc[0] == a
    return "fail closed; env/arg keys give identical tokens"
