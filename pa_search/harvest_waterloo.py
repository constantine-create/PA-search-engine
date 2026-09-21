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


def main():
    reg = {}
    for display_name, search_term in WATERLOO_ROSTER:
        m = harvest_firm(display_name, search_term, max_filings=100)
        print(f"{display_name}: {len(m)} mandates")
        is_reg, crd, warnings = brokercheck.is_registered_broker_dealer(search_term)
        reg[display_name] = {"is_registered_bd": is_reg, "crd": crd, "warnings": warnings}
        time.sleep(0.2)

    (DATA_DIR / "harvest_cache" / "_waterloo_registrations.json").write_text(json.dumps(reg, indent=2))
    print("\n=== BrokerCheck ===")
    for firm, r in reg.items():
        print(f"{firm}: registered={r['is_registered_bd']} CRD={r['crd']}")


if __name__ == "__main__":
    main()
