"""FINRA BrokerCheck client — verifies a Form D "recipient" is a real,
registered placement agent (not a random advisor/finder) and surfaces the
named broker/rep.

CONFIDENCE NOTE: same caveat as edgar_formd.py - this sandbox's egress
policy blocks api.brokercheck.finra.org (confirmed via curl, org policy
403, not transient), so this has not been exercised against a live
response. The endpoint and param names below reflect the public API the
BrokerCheck website itself calls; treat as a documented starting point to
verify on first live run, not as tested code.

For non-US firms this won't resolve anything - see companies_house.py /
fca_register.py (not yet built) for the UK equivalents that the ISQ
ground-truth example clearly used (FirstPoint Equity's card cites both an
FCA FRN and a Companies House number).
"""

from __future__ import annotations

import requests

BROKERCHECK_SEARCH = "https://api.brokercheck.finra.org/search"
BROKERCHECK_FIRM_DETAIL = "https://api.brokercheck.finra.org/search/firm/{crd}"

HEADERS = {"User-Agent": "Constantine Advisors Research mbaer@constantineadvisors.com"}


def search_firm(name: str) -> list[dict]:
    """Look up a firm by name. Returns candidate matches with CRD numbers.

    NOTE: BrokerCheck's public search UI also serves individual brokers by
    default; pass a `type=Firm` style filter if the live response mixes
    individuals and firms in a way that isn't useful here - the exact
    filter param name needs confirming on first live call.
    """
    params = {"query": name, "hl": "true", "nrows": 12, "start": 0, "r": 25, "wt": "json"}
    resp = requests.get(BROKERCHECK_SEARCH, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    hits = data.get("hits", {}).get("hits", [])
    return [hit.get("_source", hit) for hit in hits]


def get_firm_detail(crd_number: str) -> dict:
    """Full firm record by CRD: registration status, disciplinary
    disclosures, branch offices, named reps."""
    resp = requests.get(BROKERCHECK_FIRM_DETAIL.format(crd=crd_number), headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def is_registered_broker_dealer(name: str) -> tuple[bool | None, str | None, list[str]]:
    """Best-effort registration check.

    Returns (is_registered, crd_number, warnings). is_registered is None
    (not False) when the lookup itself failed or was ambiguous - callers
    should treat None as "needs a human to confirm", not as "not
    registered". A Form D recipient that ISN'T a registered BD is a real
    and useful signal (unregistered finder, in-house IR, or a data-entry
    quirk) but should never be silently coerced to a hard False from an
    API error.
    """
    warnings: list[str] = []
    try:
        hits = search_firm(name)
    except requests.RequestException as exc:
        return None, None, [f"BrokerCheck lookup failed: {exc}"]

    if not hits:
        return None, None, ["no BrokerCheck match found for this name"]
    if len(hits) > 1:
        warnings.append(f"{len(hits)} BrokerCheck matches for {name!r} - taking the first, confirm manually")

    top = hits[0]
    crd = top.get("firm_crd_nb") or top.get("crd_number") or top.get("org_source_id")
    return True, crd, warnings
