from pathlib import Path

from pa_search.build_waterloo_shortlist import build_candidates
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


def render(prioritize_boutique: bool = False) -> Path:
    gp, candidates = build_candidates(enrich_location=True, prioritize_boutique=prioritize_boutique)
    suffix = "_Boutique_Priority" if prioritize_boutique else ""
    out_path = OUTPUT_DIR / f"Waterloo_Associates_Fund_III_Placement_Agent_Shortlist{suffix}.pdf"
    render_pdf(gp, candidates, str(out_path),
               intro_note=BOUTIQUE_INTRO if prioritize_boutique else INTRO)
    return out_path


if __name__ == "__main__":
    out_path = render(prioritize_boutique=True)
    print(f"Wrote {out_path}")
