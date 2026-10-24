"""Status / label vocabularies and state / postal-code normalisation."""

import re

from .reference import _R
from .utils import _blank, _norm_label


def normalize_status(raw, ref=None):
    ref = _R(ref)
    if _blank(raw): return None, "STATUS_UNKNOWN"
    v = ref.status_map.get(_norm_label(raw))
    return (v, None) if v else (None, "STATUS_UNKNOWN")

def normalize_label(raw, mapping, issue_code):
    if _blank(raw): return None, None
    v = mapping.get(_norm_label(raw))
    return (v, None) if v else (None, issue_code)

# ---- Scenario 7: state / postal code -------------------------------------------
def _codes(s): return {k.strip(): v.strip() for k, v in (p.split(":") for p in s.split(","))}

_STATES = {
 "US": _codes("AL:Alabama,AK:Alaska,AZ:Arizona,AR:Arkansas,CA:California,CO:Colorado,CT:Connecticut,DE:Delaware,DC:District of Columbia,FL:Florida,GA:Georgia,HI:Hawaii,ID:Idaho,IL:Illinois,IN:Indiana,IA:Iowa,KS:Kansas,KY:Kentucky,LA:Louisiana,ME:Maine,MD:Maryland,MA:Massachusetts,MI:Michigan,MN:Minnesota,MS:Mississippi,MO:Missouri,MT:Montana,NE:Nebraska,NV:Nevada,NH:New Hampshire,NJ:New Jersey,NM:New Mexico,NY:New York,NC:North Carolina,ND:North Dakota,OH:Ohio,OK:Oklahoma,OR:Oregon,PA:Pennsylvania,RI:Rhode Island,SC:South Carolina,SD:South Dakota,TN:Tennessee,TX:Texas,UT:Utah,VT:Vermont,VA:Virginia,WA:Washington,WV:West Virginia,WI:Wisconsin,WY:Wyoming"),
 "IN": _codes("AP:Andhra Pradesh,AR:Arunachal Pradesh,AS:Assam,BR:Bihar,CG:Chhattisgarh,GA:Goa,GJ:Gujarat,HR:Haryana,HP:Himachal Pradesh,JH:Jharkhand,KA:Karnataka,KL:Kerala,MP:Madhya Pradesh,MH:Maharashtra,MN:Manipur,ML:Meghalaya,MZ:Mizoram,NL:Nagaland,OD:Odisha,PB:Punjab,RJ:Rajasthan,SK:Sikkim,TN:Tamil Nadu,TS:Telangana,TR:Tripura,UP:Uttar Pradesh,UK:Uttarakhand,WB:West Bengal,AN:Andaman and Nicobar Islands,CH:Chandigarh,DN:Dadra and Nagar Haveli and Daman and Diu,DL:Delhi,JK:Jammu and Kashmir,LA:Ladakh,LD:Lakshadweep,PY:Puducherry"),
 "BR": _codes("AC:Acre,AL:Alagoas,AP:Amapa,AM:Amazonas,BA:Bahia,CE:Ceara,DF:Distrito Federal,ES:Espirito Santo,GO:Goias,MA:Maranhao,MT:Mato Grosso,MS:Mato Grosso do Sul,MG:Minas Gerais,PA:Para,PB:Paraiba,PR:Parana,PE:Pernambuco,PI:Piaui,RJ:Rio de Janeiro,RN:Rio Grande do Norte,RS:Rio Grande do Sul,RO:Rondonia,RR:Roraima,SC:Santa Catarina,SP:Sao Paulo,SE:Sergipe,TO:Tocantins"),
}

def _ascii(s): return re.sub(r"[^a-z ]", "", re.sub(r"\s+", " ", str(s).lower().replace("ã", "a").replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ô", "o").replace("ú", "u").replace("ç", "c").replace("â", "a").replace("ê", "e")).strip())

_STATE_LOOKUP = {c: {**{k.lower(): k for k in m}, **{_ascii(v): k for k, v in m.items()}} for c, m in _STATES.items()}

_POSTAL = {"IN": (re.compile(r"^\d{6}$"), lambda d: d), "US": (re.compile(r"^\d{5}(-\d{4})?$"), lambda d: d),
           "BR": (re.compile(r"^\d{8}$"), lambda d: f"{d[:5]}-{d[5:]}"),
           "GB": (re.compile(r"^[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}$"), lambda d: d if " " in d else f"{d[:-3]} {d[-3:]}")}

def normalize_state(raw, country):
    """-> (ISO-style state code | None, issue). Unknown states are NOT guessed."""
    if _blank(raw) or country not in _STATE_LOOKUP: return None, None
    k = _STATE_LOOKUP[country].get(_ascii(raw)) or _STATE_LOOKUP[country].get(str(raw).strip().lower())
    return (k, None) if k else (None, "STATE_UNMAPPED")

def normalize_postal(raw, country):
    """-> (canonical postal code | None, issue). Pattern-validated per country; leading zeros are never added."""
    if _blank(raw) or country not in _POSTAL: return None, None
    rx, fmt = _POSTAL[country]; s = str(raw).strip().upper()
    s = re.sub(r"[\s-]", "", s) if country == "BR" else (re.sub(r"\s+", " ", s) if country == "GB" else re.sub(r"\s+", "", s))
    s = s[:-2] if re.fullmatch(r"\d+\.0", s) else s
    return (fmt(s), None) if rx.fullmatch(s) else (None, "POSTAL_INVALID")
