"""Assemble the real harvested Form D data into scored, composed output -
the actual end-to-end deliverable: live data in, ranked shortlist out.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pa_search.compose import render_shortlist
from pa_search.gp_intake import load_profile
from pa_search.harvest_gbf import GBF_ROSTER, CACHE_DIR
from pa_search.models import Mandate, PAFirm, ScoredCandidate, SourceTrust
from pa_search.scoring import score_candidate

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR = Path(__file__).parent.parent / "output"


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    return date.fromisoformat(s)


def _strip_cik_suffix(fund_name: str) -> str:
    # Harvested fund_name values carry a trailing "  (CIK 0001234567)" that
    # the hand-written classification list doesn't - normalize both sides
    # to this form so lookups actually match. (Found live: without this,
    # EVERY classification lookup silently missed, since the classification
    # list was written without CIK suffixes - domain_specificity was 0 for
    # every firm, and the fix appeared to "work" only because of an
    # unrelated tie-break coincidence. Never re-introduce an exact match
    # against the raw fund_name field.)
    return fund_name.split("  (CIK")[0].strip()


def load_sector_classification() -> tuple[set[str], set[str]]:
    path = DATA_DIR / "sector_classification" / "gbf_biotech_classification.json"
    data = json.loads(path.read_text())
    return set(data["biotech_specific"]), set(data["healthcare_broad"])


def load_firm(display_name: str, search_term: str, bd_registration: dict,
              biotech_names: set[str], healthcare_names: set[str]) -> PAFirm:
    cache_path = CACHE_DIR / f"{display_name.replace(' ', '_').replace('/', '-')}.json"
    raw_mandates = json.loads(cache_path.read_text()) if cache_path.exists() else []

    mandates = []
    for m in raw_mandates:
        sold = m.get("total_amount_sold")
        amount = float(sold) / 1_000_000 if sold and sold != "0" else None
        fund = _strip_cik_suffix(m["fund_name"])
        if fund in biotech_names:
            sector_tags = ["biotech", "healthcare"]
        elif fund in healthcare_names:
            sector_tags = ["healthcare"]
        else:
            sector_tags = []
        mandates.append(
            Mandate(
                pa_firm=display_name,
                fund_name=m["fund_name"],
                gp_name=None,
                amount_usd_m=amount,
                amount_is_target=False,
                sector_tags=sector_tags,
                close_or_filing_date=_parse_date(m.get("file_date")),
                role="recipient of record (SEC Form D)",
                source_url=m.get("source_url"),
                source_trust=SourceTrust.PRIMARY,
                raw_claim=f"SEC Form D recipient match: {m.get('matched_recipient_name')}",
                verification_note=f"CRD on filing: {m.get('recipient_crd')}",
            )
        )

    reg = bd_registration.get(display_name, {})
    return PAFirm(
        name=display_name,
        hq="(not yet enriched - needs firm website/BrokerCheck address lookup)",
        crd_number=reg.get("crd"),
        is_registered_broker_dealer=reg.get("is_registered_bd"),
        region="United States",
        mandates=mandates,
    )


def main() -> None:
    gp = load_profile(DATA_DIR / "gp_profiles" / "global_bioaccess_fund.json")
    reg = json.loads((DATA_DIR / "harvest_cache" / "_summary.json").read_text())["registrations"] \
        if (DATA_DIR / "harvest_cache" / "_summary.json").exists() else {}

    as_of = date(2026, 9, 21)
    biotech_names, healthcare_names = load_sector_classification()
    candidates = []
    for display_name, search_term in GBF_ROSTER:
        firm = load_firm(display_name, search_term, reg, biotech_names, healthcare_names)
        score = score_candidate(firm, gp, as_of, require_boutique=False)
        n_mandates = len(firm.mandates)
        n_biotech = len([m for m in firm.mandates if "biotech" in m.sector_tags])
        n_healthcare = len([m for m in firm.mandates if m.sector_tags])
        thesis = (
            f"{n_mandates} SEC Form D mandates found where this firm is a listed sales-compensation "
            f"recipient (2019-2026); {n_healthcare} healthcare-relevant, {n_biotech} biotech-specific "
            f"(manually classified by fund identity, not keyword-matched - see "
            f"data/sector_classification/gbf_biotech_classification.json)."
        )
        candidates.append(ScoredCandidate(firm=firm, score=score, thesis=thesis))

    candidates.sort(key=lambda c: c.score.total, reverse=True)

    doc = render_shortlist(
        gp=gp,
        candidates=candidates,
        also_considered=[],
        as_of=as_of,
        universe_note=f"{len(GBF_ROSTER)}-firm seed roster cross-checked live against SEC EDGAR Form D "
                       f"full-text search + FINRA BrokerCheck",
        mandates_traced=sum(len(c.firm.mandates) for c in candidates),
    )

    out_path = OUTPUT_DIR / "gbf_shortlist_live.md"
    out_path.write_text(doc)
    print(f"Wrote {out_path}")

    print("\n=== RANKING (live data) vs GROUND TRUTH ===")
    # Hand-verified mapping from GBF_ROSTER display names to the ground-truth
    # doc's exact entries (fuzzy string matching on these names is unreliable -
    # tried it, got false positives like "Evercore" matching "UBS" on shared
    # words like "Private Funds Group" - a manual map is more honest here
    # since both files were authored in this same session).
    GT_RANK = {
        "Atlantic-Pacific Capital": 1, "Eaton Partners": 2, "Asante Capital Group": 3,
        "Probitas Partners": 4, "Houlihan Lokey Private Funds Group": 5, "Snowbridge Advisors": 6,
        "Monument Group": 7, "Capstone Partners (Mizuho)": 8, "Pacenote Capital": 9,
        "Harris Williams Private Capital Advisory": 10, "UBS Private Funds Group": 11,
        "Lazard Private Capital Advisory": "also-considered", "William Blair": "also-considered",
        "Metric Point Capital": "also-considered", "Harken Capital Securities": "also-considered",
        "Strathmore Group": "also-considered", "Evercore Private Funds Group": "also-considered",
        "PJT Park Hill": "also-considered",
    }
    for i, c in enumerate(candidates, start=1):
        gt_r = GT_RANK.get(c.firm.name, "?")
        print(f"live #{i:2}  (ground truth: {gt_r!s:>16})  score={c.score.total:>5}  {c.firm.name}")


if __name__ == "__main__":
    main()
