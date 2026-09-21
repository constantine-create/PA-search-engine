"""FINRA BrokerCheck client — verifies a Form D "recipient" is a real,
registered placement agent (not a random advisor/finder) and surfaces the
named broker/rep.

VALIDATED LIVE 2026-09-21 once this environment's network policy was set
to Full access. The endpoint originally written here (`/search`) was
wrong - AWS API Gateway returned "MissingAuthenticationTokenException",
which despite the name just means no route matched, not that auth is
required. The real path is `/search/firm`, and it needs a Referer header
or Cloudflare blocks it. Confirmed against Atlantic-Pacific Capital: CRD
38356, which matches the recipientCRDNumber pulled independently from a
real Form D filing via edgar_formd.py - the two sources cross-reference
correctly.

For non-US firms this won't resolve anything - see companies_house.py /
fca_register.py (not yet built) for the UK equivalents that the ISQ
ground-truth example clearly used (FirstPoint Equity's card cites both an
FCA FRN and a Companies House number).
"""

from __future__ import annotations

import requests

BROKERCHECK_FIRM_SEARCH = "https://api.brokercheck.finra.org/search/firm"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Constantine Advisors Research mbaer@constantineadvisors.com)",
    "Referer": "https://brokercheck.finra.org/",
}


def search_firm(name: str) -> list[dict]:
    """Look up a firm by name. Returns candidate matches with CRD numbers
    (field: firm_bd_sec_number) and active/registered status (firm_scope).
    """
    params = {
        "query": name,
        "filter": "active=true",
        "includePrevious": "true",
        "hl": "true",
        "nrows": 12,
        "start": 0,
        "r": 25,
        "sort": "score desc",
        "wt": "json",
    }
    resp = requests.get(BROKERCHECK_FIRM_SEARCH, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    hits = data.get("hits", {}).get("hits", [])
    return [hit.get("_source", hit) for hit in hits]


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
    # firm_source_id is BrokerCheck's CRD number and is what matches Form D's
    # recipientCRDNumber (confirmed: Atlantic-Pacific Capital = 38356 in both).
    # firm_bd_sec_number is a DIFFERENT identifier (the SEC file number, e.g.
    # "48198" for the same firm) - do not confuse the two.
    crd = top.get("firm_source_id")
    scope = (top.get("firm_scope") or "").upper()
    is_registered = "ACTIV" in scope if scope else None
    return is_registered, crd, warnings
