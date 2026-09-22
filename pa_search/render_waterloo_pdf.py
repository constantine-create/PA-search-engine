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

if __name__ == "__main__":
    gp, candidates = build_candidates(enrich_location=True)
    out_path = OUTPUT_DIR / "Waterloo_Associates_Fund_III_Placement_Agent_Shortlist.pdf"
    render_pdf(gp, candidates, str(out_path), intro_note=INTRO)
    print(f"Wrote {out_path}")
