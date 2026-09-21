"""Real, live harvest run against Global Bioaccess Fund's roster (the 18
GBF-relevant firms from the ground truth: 11 ranked + 7 also-considered).

This is the actual proof-of-concept: for each firm, search SEC EDGAR full
text search for Form D filings mentioning them, fetch each filing's XML,
confirm the firm really is a listed sales-compensation recipient (full
text search matches anywhere in the filing, not just that field - false
positives get discarded here), and keep the ones that are a genuine
biotech/healthcare fund by a simple keyword heuristic on the issuer name
(Form D itself has no therapeutic-area field).

Rate-limited to stay well under SEC's guidance (max ~10 req/sec); this
script is deliberately conservative given it's the first live run.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

from pa_search.sources import edgar_formd, brokercheck

DATA_DIR = Path(__file__).parent.parent / "data"
CACHE_DIR = DATA_DIR / "harvest_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# (display name used in output, search term used against Form D full text search)
# Full display names like "Houlihan Lokey Private Funds Group" rarely appear
# verbatim on a filing - Form D recipient fields use the firm's shorter legal/
# brand name. Confirmed by diagnostic: searching "Houlihan Lokey" alone finds
# 70 hits including Revelstoke III/II (exactly what the ground-truth doc cites
# for this firm), where the full display name found 0.
GBF_ROSTER = [
    ("Atlantic-Pacific Capital", "Atlantic-Pacific Capital"),
    ("Eaton Partners", "Eaton Partners"),
    ("Asante Capital Group", "Asante Capital"),
    ("Probitas Partners", "Probitas Partners"),
    ("Houlihan Lokey Private Funds Group", "Houlihan Lokey"),
    ("Snowbridge Advisors", "Snowbridge"),
    ("Monument Group", "Monument Group"),
    ("Capstone Partners (Mizuho)", "Capstone Partners"),
    ("Pacenote Capital", "Pacenote Capital"),
    ("Harris Williams Private Capital Advisory", "Harris Williams"),
    ("UBS Private Funds Group", "UBS Securities"),
    ("Lazard Private Capital Advisory", "Lazard"),
    ("William Blair", "William Blair"),
    ("Metric Point Capital", "Metric Point Capital"),
    ("Harken Capital Securities", "Harken Capital"),
    ("Strathmore Group", "Strathmore Group"),
    ("Evercore Private Funds Group", "Evercore"),
    ("PJT Park Hill", "PJT Park Hill"),
]

BIOTECH_KEYWORDS = [
    "health", "bio", "pharma", "therapeutic", "oncology", "clinical", "life science",
    "medtech", "medical", "genom", "immun", "vivo", "clinic", "pharmaceutical",
]


def _name_match(search_term: str, candidate: str, threshold: float = 0.55) -> bool:
    """True if candidate is plausibly the same firm as search_term.

    Substring containment handles the common case (search_term is a short
    brand name, candidate is the fuller legal name, e.g. "Eaton Partners"
    vs "Eaton Partners, LLC" or "Eaton Partners (Stifel)"). Fuzzy ratio is
    a fallback for near-matches that aren't clean substrings. Pure
    SequenceMatcher ratio alone was too strict for short-vs-long name
    pairs like "UBS Securities" vs "UBS Financial Services Inc." and
    silently dropped real matches.
    """
    if not candidate:
        return False
    s, c = search_term.lower().strip(), candidate.lower().strip()
    if s in c or c in s:
        return True
    return SequenceMatcher(None, s, c).ratio() >= threshold


def is_biotech_relevant(issuer_name: str) -> bool:
    low = issuer_name.lower()
    return any(kw in low for kw in BIOTECH_KEYWORDS)


def _with_retry(fn, attempts=3, base_delay=1.5):
    last_exc = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            msg = str(e)
            if "500" in msg or "503" in msg:
                time.sleep(base_delay * (i + 1))
                continue
            raise
    raise last_exc


def harvest_firm(display_name: str, search_term: str, max_filings: int = 30) -> list[dict]:
    cache_path = CACHE_DIR / f"{display_name.replace(' ', '_').replace('/', '-')}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    print(f"harvesting: {display_name} (search: {search_term!r})")
    try:
        hits = _with_retry(lambda: edgar_formd.search_form_d(f'"{search_term}"', "2019-01-01", "2026-09-21"))
    except Exception as e:
        print(f"  search failed: {e}")
        return []

    mandates = []
    seen_issuers = set()
    for hit in hits[:max_filings]:
        adsh = hit.get("adsh")
        ciks = hit.get("ciks", [])
        if not adsh or not ciks:
            continue
        issuer_display = hit.get("display_names", ["?"])[0]
        if issuer_display in seen_issuers:
            continue
        seen_issuers.add(issuer_display)

        time.sleep(0.15)  # stay well under SEC's rate guidance
        try:
            xml = _with_retry(lambda: edgar_formd.fetch_form_d_xml(ciks[0], adsh))
        except Exception as e:
            print(f"  fetch failed for {adsh}: {e}")
            continue

        recipients = edgar_formd.parse_recipients_from_xml(xml)
        matched = [
            r for r in recipients
            if _name_match(search_term, r.get("recipientName", "")) or
               _name_match(search_term, r.get("associatedBDName", ""))
        ]
        if not matched:
            continue  # firm was mentioned somewhere in the filing, but not as the recipient - discard

        amounts = edgar_formd.parse_offering_amounts(xml)
        mandates.append(
            {
                "pa_firm": display_name,
                "fund_name": issuer_display,
                "file_date": hit.get("file_date"),
                "accession": adsh,
                "total_offering_amount": amounts.get("totalOfferingAmount"),
                "total_amount_sold": amounts.get("totalAmountSold"),
                "recipient_crd": matched[0].get("recipientCRDNumber"),
                "matched_recipient_name": matched[0].get("recipientName"),
                "is_biotech_relevant_by_name": is_biotech_relevant(issuer_display),
                "source_url": edgar_formd.filing_xml_url(ciks[0], adsh),
            }
        )

    cache_path.write_text(json.dumps(mandates, indent=2))
    return mandates


def harvest_all(roster: list[tuple[str, str]] = GBF_ROSTER) -> dict[str, list[dict]]:
    out = {}
    for display_name, search_term in roster:
        out[display_name] = harvest_firm(display_name, search_term)
        time.sleep(0.2)
    return out


def verify_all_registrations(roster: list[tuple[str, str]] = GBF_ROSTER) -> dict[str, dict]:
    out = {}
    for display_name, search_term in roster:
        is_reg, crd, warnings = _with_retry(lambda: brokercheck.is_registered_broker_dealer(search_term))
        out[display_name] = {"is_registered_bd": is_reg, "crd": crd, "warnings": warnings}
        time.sleep(0.2)
    return out


if __name__ == "__main__":
    mandates = harvest_all()
    reg = verify_all_registrations()

    print("\n=== SUMMARY ===")
    for firm, m_list in mandates.items():
        biotech = [m for m in m_list if m["is_biotech_relevant_by_name"]]
        r = reg.get(firm, {})
        print(f"{firm}: {len(m_list)} confirmed mandates ({len(biotech)} biotech-relevant by name), "
              f"BrokerCheck: registered={r.get('is_registered_bd')} CRD={r.get('crd')}")

    (DATA_DIR / "harvest_cache" / "_summary.json").write_text(
        json.dumps({"mandates": mandates, "registrations": reg}, indent=2)
    )
