"""Assemble the real harvested Form D data for Waterloo Associates Fund
III into a scored, composed shortlist. No ground truth exists for this
one - this is the actual blind deliverable, not a validation run.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pa_search.build_gbf_shortlist import _strip_cik_suffix, load_firm
from pa_search.compose import render_shortlist
from pa_search.gp_intake import load_profile
from pa_search.harvest_waterloo import EXCLUDED_V3, WATERLOO_ROSTER, WATERLOO_ROSTER_V3
from pa_search.models import Mandate, PAFirm, ScoredCandidate, SourceTrust
from pa_search.scoring import score_candidate, score_lp_fit
from pa_search.sources import brokercheck

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

AS_OF = date(2026, 9, 21)

# Boutique-vs-platform judgment calls, made 2026-09-30 for the boutique-priority
# rerun. "Boutique" here means independent and small/mid-size enough to plausibly
# treat a $200M land-development raise as a priority relationship, not one
# platform's marginal mandate among many much larger ones. Bank/bulge-bracket-
# owned desks (Stifel, Evercore, Lazard, Houlihan Lokey, PJT Partners) are marked
# False regardless of the specialist team's own quality, because the parent
# platform's economics and deal flow skew toward much larger raises.
BOUTIQUE_CLASSIFICATION = {
    "Atlantic-Pacific Capital": False,   # global multi-office, high mandate volume - not prioritizing small deals
    "Probitas Partners": True,            # independent, own broker-dealer, mid-size
    "Eaton Partners": False,               # part of Stifel (large bank)
    "Monument Group": True,                 # independent boutique
    "PJT Park Hill": False,                  # part of PJT Partners (large bank)
    "Evercore Private Funds Group": False,    # part of Evercore (bulge-bracket)
    "Lazard Private Capital Advisory": False,  # part of Lazard (bulge-bracket)
    "Houlihan Lokey Private Funds Group": False,  # part of Houlihan Lokey (large advisory firm)
    "Hodes Weill & Associates": True,          # real estate specialist, but ACQUIRED by Chatham Financial
                                                 # in 2026 - flagged as a caveat, not a hard exclusion
    "Park Madison Partners": True,               # independent real-assets boutique, est. 2006
    "Campbell Lutyens": False,                    # sizable independent (~100+ globally) - not a small shop
    "Mercury Capital Advisors": True,               # independent, moderate size
    "Threadmark": True,                              # independent real estate specialist
    "Sixpoint Partners": True,                        # independent boutique
    "Castle Placement": True,                          # small FINRA-registered shop, Long Beach NY office
    # Added for the third (family-office boutique) report, 2026-09-30. All four are
    # independent FINRA broker-dealers with 2-6 registered branches on BrokerCheck.
    "Accord Capital Partners": True,                    # SF real estate capital-advisory BD, 2 branches
    "Kipling Capital": True,                             # Mill Valley CA, placement agent since 1999, 3 branches
    "Harken Capital Securities": True,                    # ~6 employees, Boston-area fund placement
    "Invicta Capital": True,                               # Oakmont PA BD, affiliated with an RIA
}

# Third report only. LP types each firm demonstrably covers, drawn from the firm's own
# materials or its directory profile (source noted per firm), NOT inferred from mandates.
# Values are matched against the GP profile's target_lp_types by scoring.score_lp_fit.
# Where the evidence is thin the list is deliberately short: an omission scores 0, a
# guess would inflate a firm's rank on a claim we cannot back.
V3_LP_COVERAGE = {
    "Castle Placement": ["institutional", "family office"],       # castleplacement.com: network incl. family offices, pensions, endowments
    "Park Madison Partners": ["institutional"],                    # institutional real estate capital raising; no family-office claim found
    "Threadmark": ["institutional", "family office"],              # directory profile: European family offices, SWFs, pensions
    "Accord Capital Partners": ["institutional", "family office"],  # accord-group.net: "family offices, fund-of-funds"
    "Kipling Capital": ["family office", "RIA", "individual accredited investors"],  # kiplingcapital.com: advisors, HNW individuals, families, trusts
    "Harken Capital Securities": ["institutional", "family office"],  # firm profile: pensions, endowments, family offices
    "Invicta Capital": ["RIA"],                                      # affiliated RIA (Invicta Advisors); no direct statement of LP types found
}

# Third report only: what the firm's card should say beyond the generic Form D count,
# including where public profiles disagree with each other. Written to be checked, not
# to sell: the caveats are the point.
V3_NOTES = {
    "Castle Placement": (
        "Public profiles describe a New York capital-raising investment bank (est. 2009) with a large investor "
        "network including family offices; BrokerCheck registers the firm at a Long Beach, NY address. Real estate "
        "is one of many sectors it covers, and the Form D history is broad (operating companies and funds), so the "
        "real-estate track record is thin."),
    "Park Madison Partners": (
        "Real estate-only capital raiser, formed 2006, advertising over $20B of private placements. Institutional "
        "focus; no family-office positioning found in public materials."),
    "Threadmark": (
        "Public profiles describe Threadmark as London-headquartered (est. 2009) with relationships across "
        "European family offices and Middle Eastern sovereign funds. On the StepStone filings the paid "
        "recipient is Threadmark Partners Limited, a UK entity with no US CRD number; the US-registered "
        "broker-dealer is Threadmark LP (New York). Real estate is one of several strategies."),
    "Accord Capital Partners": (
        "Capital-advisory affiliate of San Francisco real estate investor Accord Group. Advertises 30+ third-party "
        "transactions (2014-2025) across multifamily, build-to-rent, hospitality and industrial; its site cites "
        "family offices as a target investor group in at least one case study. Affiliation with a principal "
        "investor should be discussed with the firm."),
    "Kipling Capital": (
        "Mill Valley firm in business 25+ years serving investment advisors, high-net-worth individuals, families "
        "and trusts; advertises $2.2B+ of equity raised across 1,000+ real estate projects. Real estate only, no "
        "land development or homebuilder offerings found. The closest fit to the small family-office brief."),
    "Harken Capital Securities": (
        "About six people, Boston area, fund placement plus secondaries for emerging and mid-size managers; LP "
        "base includes family offices. Mandates are almost entirely private equity and venture; only one real "
        "estate fund (TerraCap Partners IV) found. Included as a small-boutique lead, not a real estate specialist."),
    "Invicta Capital": (
        "Oakmont, PA broker-dealer affiliated with an RIA (Invicta Advisors). Its real estate entries are mostly "
        "DST offerings (including Sun Belt single-family and build-to-rent) on which it is one of dozens of "
        "selling broker-dealers, which is distribution, not a placement mandate. Its hedge, private equity and "
        "credit fund mandates are the better evidence of a placement business. No public description of its "
        "practice was found; treat as a lead to vet directly."),
}


def load_sector_classification() -> tuple[set[str], set[str]]:
    path = DATA_DIR / "sector_classification" / "waterloo_real_estate_classification.json"
    data = json.loads(path.read_text())
    return set(data["land_development_specific"]), set(data["real_estate_broad"])


def _castle_placement_firm() -> PAFirm:
    """No SEC Form D data available - EDGAR was blocked for this session, so
    this firm (added for the boutique-priority rerun) has no harvested
    mandate history. Included on qualitative grounds only: verified live via
    FINRA BrokerCheck (CRD 189511, active), small Long Beach NY office (a
    signal of scale, not a knock), and public positioning toward smaller
    sponsors across real estate/credit strategies. Flagged clearly in its
    card rather than presented as equivalent to the Form-D-verified firms."""
    return PAFirm(
        name="Castle Placement",
        hq="Long Beach, NY",
        crd_number="189511",
        is_registered_broker_dealer=True,
        is_boutique=True,
        region="United States",
        mandates=[],
    )


def build_candidates(enrich_location: bool = True, prioritize_boutique: bool = False) -> tuple:
    """Returns (gp, candidates) sorted best-first. Shared by the Markdown
    debug view (main()) and the client-facing PDF composer, so both read
    from the same scored data rather than recomputing it differently."""
    gp = load_profile(DATA_DIR / "gp_profiles" / "waterloo_associates_fund_iii.json")
    reg = json.loads((DATA_DIR / "harvest_cache" / "_waterloo_registrations.json").read_text())

    land_dev_names, re_names = load_sector_classification()
    candidates = []
    for display_name, search_term in WATERLOO_ROSTER:
        firm = load_firm(
            display_name, search_term, reg, land_dev_names, re_names,
            specific_tags=["land development", "real estate"], broad_tags=["real estate"],
        )
        firm.is_boutique = BOUTIQUE_CLASSIFICATION.get(display_name)
        if enrich_location:
            loc = brokercheck.get_firm_location(search_term)
            if loc:
                firm.hq = loc
        score = score_candidate(firm, gp, AS_OF, require_boutique=prioritize_boutique)
        if prioritize_boutique:
            # scoring.py's boutique cap (1.0) is too small a swing to make this
            # a real priority against firms with much larger recency/band/
            # domain scores from bigger mandate volumes - this run's brief was
            # explicit that boutique fit should be a real priority, not a
            # decorative tiebreaker, so it's weighted up here rather than by
            # changing scoring.py's shared default (which other GPs' searches
            # also use and shouldn't be skewed by this one run's preference).
            score.boutique = 4.0 if firm.is_boutique else (0.0 if firm.is_boutique is False else 2.0)
        n_mandates = len(firm.mandates)
        n_re = len([m for m in firm.mandates if m.sector_tags])
        n_land = len([m for m in firm.mandates if "land development" in m.sector_tags])
        boutique_note = {True: "independent/boutique", False: "bank- or platform-owned desk",
                          None: "boutique status not assessed"}[firm.is_boutique]
        thesis = (
            f"{n_mandates} SEC Form D mandates found where this firm is a listed sales-compensation "
            f"recipient (2019-2026); {n_re} real-estate-relevant, {n_land} residential land/"
            f"development-specific by fund identity (manually classified - see "
            f"data/sector_classification/waterloo_real_estate_classification.json). "
            f"Structure: {boutique_note}."
        )
        candidates.append(ScoredCandidate(firm=firm, score=score, thesis=thesis))

    if prioritize_boutique:
        castle = _castle_placement_firm()
        score = score_candidate(castle, gp, AS_OF, require_boutique=True)
        score.boutique = 4.0
        thesis = (
            "No SEC Form D mandate history available (EDGAR was inaccessible this session, so this "
            "entry could not be harvested like the others - added on qualitative grounds only). "
            "Verified live via FINRA BrokerCheck as an active registered broker-dealer (CRD 189511), "
            "small Long Beach, NY office, publicly positioned toward smaller fund sponsors across "
            "real estate and credit strategies. Treat as a lead to vet directly, not a verified track record."
        )
        candidates.append(ScoredCandidate(firm=castle, score=score, thesis=thesis))

    candidates.sort(key=lambda c: c.score.total, reverse=True)
    return gp, candidates


def build_candidates_v3(enrich_location: bool = True) -> tuple:
    """Third report: small independent boutiques with a family-office lean.

    Same scoring as build_candidates(prioritize_boutique=True), plus:
    - a fixed roster (three client-named anchors + sourced newcomers) checked
      against EXCLUDED_V3, so a big name can't slip back in via a roster edit;
    - lp_fit weighted up to a cap of 3.0 (default 1.0) from V3_LP_COVERAGE,
      because this run's brief was small family-office investors, and the
      shared default is too small a swing to matter against recency/band.
      Shared defaults in scoring.py are untouched.
    """
    gp = load_profile(DATA_DIR / "gp_profiles" / "waterloo_associates_fund_iii.json")
    reg = json.loads((DATA_DIR / "harvest_cache" / "_waterloo_v3_registrations.json").read_text())

    land_dev_names, re_names = load_sector_classification()
    candidates = []
    for display_name, search_term in WATERLOO_ROSTER_V3:
        assert display_name not in EXCLUDED_V3, f"{display_name} is on the exclusion list"
        firm = load_firm(
            display_name, search_term, reg, land_dev_names, re_names,
            specific_tags=["land development", "real estate"], broad_tags=["real estate"],
        )
        firm.is_boutique = BOUTIQUE_CLASSIFICATION.get(display_name)
        firm.lp_coverage = V3_LP_COVERAGE.get(display_name, [])
        if enrich_location:
            loc = brokercheck.get_firm_location(search_term)
            if loc:
                firm.hq = loc
        score = score_candidate(firm, gp, AS_OF, require_boutique=True)
        score.boutique = 4.0 if firm.is_boutique else (0.0 if firm.is_boutique is False else 2.0)
        score.lp_fit = score_lp_fit(firm, gp, cap=3.0)

        n_mandates = len(firm.mandates)
        n_re = len([m for m in firm.mandates if m.sector_tags])
        n_land = len([m for m in firm.mandates if "land development" in m.sector_tags])
        thesis = (
            f"{n_mandates} SEC Form D mandates found where this firm is a listed sales-compensation "
            f"recipient (2019-2026); {n_re} real-estate-relevant, {n_land} residential land/"
            f"development-specific by fund identity (manually classified). "
            f"{V3_NOTES[display_name]}"
        )
        candidates.append(ScoredCandidate(firm=firm, score=score, thesis=thesis))

    assert not EXCLUDED_V3 & {c.firm.name for c in candidates}
    candidates.sort(key=lambda c: c.score.total, reverse=True)
    return gp, candidates


def main() -> None:
    gp, candidates = build_candidates(enrich_location=False)

    doc = render_shortlist(
        gp=gp,
        candidates=candidates,
        also_considered=[],
        as_of=AS_OF,
        universe_note=f"{len(WATERLOO_ROSTER)}-firm roster (real-estate/real-assets specialists "
                       f"identified via live web search, plus generalist firms validated against "
                       f"SEC Form D data in the GBF prototype run) cross-checked live against SEC "
                       f"EDGAR Form D full-text search + FINRA BrokerCheck",
        mandates_traced=sum(len(c.firm.mandates) for c in candidates),
    )

    out_path = OUTPUT_DIR / "waterloo_shortlist_live.md"
    out_path.write_text(doc)
    print(f"Wrote {out_path}")

    print("\n=== RANKING ===")
    for i, c in enumerate(candidates, start=1):
        n_land = len([m for m in c.firm.mandates if "land development" in m.sector_tags])
        n_re = len([m for m in c.firm.mandates if m.sector_tags])
        print(f"#{i:2}  score={c.score.total:>5}  land={n_land} re={n_re} total={len(c.firm.mandates):>3}  {c.firm.name}")


if __name__ == "__main__":
    main()
