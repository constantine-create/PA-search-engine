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
from pa_search.models import ScoredCandidate
from pa_search.scoring import score_candidate
from pa_search.sources import brokercheck

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

AS_OF = date(2026, 9, 21)


def load_sector_classification() -> tuple[set[str], set[str]]:
    path = DATA_DIR / "sector_classification" / "waterloo_real_estate_classification.json"
    data = json.loads(path.read_text())
    return set(data["land_development_specific"]), set(data["real_estate_broad"])


def build_candidates(enrich_location: bool = True) -> tuple:
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
        if enrich_location:
            loc = brokercheck.get_firm_location(search_term)
            if loc:
                firm.hq = loc
        score = score_candidate(firm, gp, AS_OF, require_boutique=False)
        n_mandates = len(firm.mandates)
        n_re = len([m for m in firm.mandates if m.sector_tags])
        n_land = len([m for m in firm.mandates if "land development" in m.sector_tags])
        thesis = (
            f"{n_mandates} SEC Form D mandates found where this firm is a listed sales-compensation "
            f"recipient (2019-2026); {n_re} real-estate-relevant, {n_land} residential land/"
            f"development-specific by fund identity (manually classified - see "
            f"data/sector_classification/waterloo_real_estate_classification.json)."
        )
        candidates.append(ScoredCandidate(firm=firm, score=score, thesis=thesis))

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
