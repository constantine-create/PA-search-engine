import json
from pathlib import Path

from pa_search.compose_pdf import render_research_pdf

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

INTRO = (
    "This research covers introduction and placement agents relevant to Project Marigold's "
    "capital raise, focused specifically on agents with a presence in the United States and "
    "Singapore, drawn from the provided contact roster and verified independently. Marigold is "
    "a Swiss-domiciled holding company raising CHF 200 million in permanent capital from family "
    "offices to acquire and revive dormant European luxury brands. Because this is not a "
    "US-registered fund, this research relied on direct verification of each firm and contact "
    "through public sources (firm websites, trade press, professional directories) rather than "
    "regulatory filings. Every entry below reflects what could - and could not - be independently "
    "confirmed, so nothing here should be treated as verified beyond what is stated."
)

if __name__ == "__main__":
    roster = json.loads((DATA_DIR / "pa_roster" / "marigold_family_office_roster.json").read_text())
    entries = roster["entries"]

    # de-dupe the two READ Advisors rows into one firm block is not desired here -
    # individuals matter, so keep both, just sort with Singapore-office firms first
    def sort_key(e):
        return (not e.get("has_singapore_office"), not e.get("has_us_office"), e["firm_name"])

    entries_sorted = sorted(entries, key=sort_key)

    out_path = OUTPUT_DIR / "Marigold_US_Singapore_Agent_Research.pdf"
    render_research_pdf(
        title="Placement & Introduction Agent Research",
        subtitle="Project Marigold — US & Singapore Focus",
        out_path=str(out_path),
        intro_note=INTRO,
        entries=entries_sorted,
        excluded=roster.get("excluded_not_us_or_singapore"),
    )
    print(f"Wrote {out_path}")
