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

GBF_ROSTER = [
    "Atlantic-Pacific Capital", "Eaton Partners", "Asante Capital Group",
    "Probitas Partners", "Houlihan Lokey Private Funds Group", "Snowbridge Advisors",
    "Monument Group", "Capstone Partners", "Pacenote Capital",
    "Harris Williams Private Capital Advisory", "UBS Private Funds Group",
    "Lazard Private Capital Advisory", "William Blair", "Metric Point Capital",
    "Harken Capital Securities", "Strathmore Group", "Evercore Private Funds Group",
    "PJT Park Hill",
]

BIOTECH_KEYWORDS = [
    "health", "bio", "pharma", "therapeutic", "oncology", "clinical", "life science",
    "medtech", "medical", "genom", "immun", "vivo", "clinic", "pharmaceutical",
]


def _name_match(a: str, b: str, threshold: float = 0.6) -> bool:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


def is_biotech_relevant(issuer_name: str) -> bool:
    low = issuer_name.lower()
    return any(kw in low for kw in BIOTECH_KEYWORDS)


def harvest_firm(firm_name: str, max_filings: int = 15) -> list[dict]:
    cache_path = CACHE_DIR / f"{firm_name.replace(' ', '_').replace('/', '-')}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    print(f"harvesting: {firm_name}")
    try:
        hits = edgar_formd.search_form_d(f'"{firm_name}"', "2019-01-01", "2026-09-21")
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
            xml = edgar_formd.fetch_form_d_xml(ciks[0], adsh)
        except Exception as e:
            print(f"  fetch failed for {adsh}: {e}")
            continue

        recipients = edgar_formd.parse_recipients_from_xml(xml)
        matched = [
            r for r in recipients
            if _name_match(firm_name, r.get("recipientName", "")) or
               _name_match(firm_name, r.get("associatedBDName", ""))
        ]
        if not matched:
            continue  # firm was mentioned somewhere in the filing, but not as the recipient - discard

        amounts = edgar_formd.parse_offering_amounts(xml)
        mandates.append(
            {
                "pa_firm": firm_name,
                "fund_name": issuer_display,
                "file_date": hit.get("file_date"),
                "accession": adsh,
                "total_offering_amount": amounts.get("totalOfferingAmount"),
                "total_amount_sold": amounts.get("totalAmountSold"),
                "recipient_crd": matched[0].get("recipientCRDNumber"),
                "is_biotech_relevant_by_name": is_biotech_relevant(issuer_display),
                "source_url": edgar_formd.filing_xml_url(ciks[0], adsh),
            }
        )

    cache_path.write_text(json.dumps(mandates, indent=2))
    return mandates


def harvest_all(roster: list[str] = GBF_ROSTER) -> dict[str, list[dict]]:
    out = {}
    for firm in roster:
        out[firm] = harvest_firm(firm)
        time.sleep(0.2)
    return out


def verify_all_registrations(roster: list[str] = GBF_ROSTER) -> dict[str, dict]:
    out = {}
    for firm in roster:
        is_reg, crd, warnings = brokercheck.is_registered_broker_dealer(firm)
        out[firm] = {"is_registered_bd": is_reg, "crd": crd, "warnings": warnings}
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
