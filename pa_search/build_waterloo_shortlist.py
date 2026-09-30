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
from pa_search.harvest_waterloo import WATERLOO_ROSTER
from pa_search.models import Mandate, PAFirm, ScoredCandidate, SourceTrust
from pa_search.scoring import score_candidate
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
