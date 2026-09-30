from pathlib import Path

from pa_search.build_waterloo_shortlist import V3_NOTES, build_candidates, build_candidates_v3
from pa_search.compose_pdf import render_pdf

OUTPUT_DIR = Path(__file__).parent.parent / "output"

INTRO = (
    "Waterloo Associates Fund III, LP is a $200 million structured residential land development "
    "fund. The strategy acquires land and finished lots pre-committed to leading U.S. homebuilders, "
    "primarily across Sun Belt markets, targeting a 17%+ cash yield with limited exposure to "
    "vertical construction risk."
)

BOUTIQUE_INTRO = INTRO + (
    " This search prioritizes independent, boutique placement agents over bank- or platform-owned "
    "desks (e.g. those affiliated with Stifel, Evercore, Lazard, Houlihan Lokey, or PJT Partners). "
    "The reasoning: a $200M raise from a three-fund, non-bulge-bracket sponsor is a small mandate "
    "for a large platform juggling much bigger raises, but a genuine priority relationship for an "
    "independent boutique. Firm structure (independent vs. platform-owned) is weighted explicitly "
    "in the ranking below, alongside - not instead of - each firm's actual track record."
)


FAMILY_OFFICE_BOUTIQUE_INTRO = INTRO + (
    " This third search narrows the field to small, independent boutiques, following feedback on the first "
    "two reports. The twelve firms not carried forward are excluded: the bank- or platform-owned desks "
    "(Stifel/Eaton, Evercore, Lazard, Houlihan Lokey, PJT Park Hill, Atlantic-Pacific, Campbell Lutyens) and "
    "the larger independents (Monument Group, Hodes Weill, Mercury Capital, Sixpoint, Probitas). Castle "
    "Placement, Park Madison Partners and Threadmark, the three identified as the right size, are kept as "
    "reference points. Further firms were sourced using the search terms family office and single-family "
    "office (with Aceana Group, a Florida single-family office, as the reference investor), alongside real "
    "estate, land development, homebuilder finance and Sun Belt. A firm was kept only if it is an active "
    "FINRA-registered broker-dealer that raises capital for third-party managers; in-house capital-raising "
    "arms of sponsors were left out because they cannot be hired as independent agents. Ranking weights "
    "independent structure and demonstrated coverage of family-office and smaller private-investor bases "
    "alongside real estate track record. We could not identify a land-development-specific fund among any of "
    "these firms' filed mandates, so all are best read as introductions to the family-office channel, not as "
    "land-banking specialists. Where public profiles disagree or the evidence is thin, the entry says so."
)


def render(prioritize_boutique: bool = False) -> Path:
    gp, candidates = build_candidates(enrich_location=True, prioritize_boutique=prioritize_boutique)
    suffix = "_Boutique_Priority" if prioritize_boutique else ""
    out_path = OUTPUT_DIR / f"Waterloo_Associates_Fund_III_Placement_Agent_Shortlist{suffix}.pdf"
    render_pdf(gp, candidates, str(out_path),
               intro_note=BOUTIQUE_INTRO if prioritize_boutique else INTRO)
    return out_path


def render_v3() -> Path:
    gp, candidates = build_candidates_v3(enrich_location=True)
    out_path = OUTPUT_DIR / "Waterloo_Associates_Fund_III_Placement_Agent_Shortlist_Family_Office_Boutiques.pdf"
    render_pdf(gp, candidates, str(out_path), intro_note=FAMILY_OFFICE_BOUTIQUE_INTRO,
               firm_notes=V3_NOTES)
    return out_path


if __name__ == "__main__":
    import sys

    out_path = render_v3() if "--v3" in sys.argv else render(prioritize_boutique=True)
    print(f"Wrote {out_path}")
