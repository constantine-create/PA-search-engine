"""Live harvest for Waterloo Associates Fund III - a real estate / land
development strategy, a very different asset class from GBF (biotech) and
ISQ (infra/growth VC). Reuses the GBF harvest cache for generalist firms
already validated there (Atlantic-Pacific, Probitas, Eaton, Monument, PJT
Park Hill, Evercore, Lazard, Houlihan Lokey - same underlying SEC data,
no reason to re-fetch), and harvests fresh for real-estate/real-assets
specialists identified via live web search: Hodes Weill & Associates and
Park Madison Partners (both confirmed real-estate/real-assets capital
advisory specialists), Campbell Lutyens, Mercury Capital Advisors,
Threadmark, and Sixpoint Partners.
"""

from __future__ import annotations

from pa_search.harvest_gbf import harvest_firm, GBF_ROSTER as _GBF_ROSTER
from pa_search.sources import brokercheck
import time
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

REUSED_FROM_GBF = [
    ("Atlantic-Pacific Capital", "Atlantic-Pacific Capital"),
    ("Probitas Partners", "Probitas Partners"),
    ("Eaton Partners", "Eaton Partners"),
    ("Monument Group", "Monument Group"),
    ("PJT Park Hill", "PJT Park Hill"),
    ("Evercore Private Funds Group", "Evercore"),
    ("Lazard Private Capital Advisory", "Lazard"),
    ("Houlihan Lokey Private Funds Group", "Houlihan Lokey"),
]

NEW_RE_SPECIALISTS = [
    ("Hodes Weill & Associates", "Hodes Weill"),
    ("Park Madison Partners", "Park Madison Partners"),
    ("Campbell Lutyens", "Campbell Lutyens"),
    ("Mercury Capital Advisors", "Mercury Capital Advisors"),
    ("Threadmark", "Threadmark"),
    ("Sixpoint Partners", "Sixpoint Partners"),
]

WATERLOO_ROSTER = REUSED_FROM_GBF + NEW_RE_SPECIALISTS

# Third report (2026-09-30): the client felt only Castle Placement, Park Madison
# Partners and Threadmark read as small boutiques and asked for the other names
# to be dropped, with a focus on small family-office-oriented boutiques like
# those three. The three stay as anchors; the other 12 firms from the second
# report are excluded. Every other firm below was sourced fresh (web search plus
# SEC Form D bulk data on land / real-estate offerings), then confirmed as an
# active FINRA broker-dealer on BrokerCheck. Sponsor-captive capital-raising
# arms (Partners Finance, Shopoff Securities, Peachtree PC Investors) were
# considered and left out: they raise only for their own affiliates, so a third
# party like Waterloo cannot hire them as an independent placement agent.
ANCHORS_V3 = [
    ("Castle Placement", "Castle Placement"),
    ("Park Madison Partners", "Park Madison Partners"),
    ("Threadmark", "Threadmark"),
]

NEW_BOUTIQUES_V3 = [
    ("Accord Capital Partners", "Accord Capital Partners"),
    ("Kipling Capital", "Kipling Capital"),
    ("Harken Capital Securities", "Harken Capital"),
    ("Invicta Capital", "Invicta Capital"),
]
# Sourced and checked but not carried into the report (reason recorded so a later
# rerun doesn't re-add them): Greenwich Capital Partners (CRD 305693) - 4 Form D
# mandates, none real estate. Crito Capital, Acalyx Advisors, M2O Private Fund
# Advisors - private equity / infrastructure placement, no real estate history.
# Champlain Advisors - global 50+ person network, not small. A5 Securities - Reg A
# REIT selling group, not fund placement.

WATERLOO_ROSTER_V3 = ANCHORS_V3 + NEW_BOUTIQUES_V3

# Terms used to source the V3 roster (web search plus a scan of SEC Form D bulk data
# sets 2023Q1-2026Q1 for recipients paid on land / real-estate offerings). Aceana Group
# (aceanagroup.com) is a Key Biscayne single-family office, i.e. the target investor
# type, NOT a placement agent - it is a search keyword and reference LP only.
SEARCH_KEYWORDS_V3 = [
    "Aceana Group", "single-family office", "family office", "family office investors",
    "emerging / small fund sponsors", "real estate", "land development", "residential land",
    "homebuilder finance", "lot banking", "Sun Belt", "$100M-$300M raise",
]

EXCLUDED_V3 = {
    "Monument Group", "Hodes Weill & Associates", "Mercury Capital Advisors",
    "Sixpoint Partners", "Probitas Partners", "Atlantic-Pacific Capital",
    "Eaton Partners", "PJT Park Hill", "Evercore Private Funds Group",
    "Lazard Private Capital Advisory", "Houlihan Lokey Private Funds Group",
    "Campbell Lutyens",
}

assert not EXCLUDED_V3 & {name for name, _ in WATERLOO_ROSTER_V3}


def main(roster=None, registrations_file="_waterloo_registrations.json"):
    roster = roster or WATERLOO_ROSTER
    reg = {}
    for display_name, search_term in roster:
        m = harvest_firm(display_name, search_term, max_filings=100)
        print(f"{display_name}: {len(m)} mandates")
        is_reg, crd, warnings = brokercheck.is_registered_broker_dealer(search_term)
        reg[display_name] = {"is_registered_bd": is_reg, "crd": crd, "warnings": warnings}
        time.sleep(0.2)

    (DATA_DIR / "harvest_cache" / registrations_file).write_text(json.dumps(reg, indent=2))
    print("\n=== BrokerCheck ===")
    for firm, r in reg.items():
        print(f"{firm}: registered={r['is_registered_bd']} CRD={r['crd']}")


if __name__ == "__main__":
    import sys

    if "--v3" in sys.argv:
        main(WATERLOO_ROSTER_V3, "_waterloo_v3_registrations.json")
    else:
        main()
