"""Orchestrator CLI - wires intake -> harvest -> verify -> score -> compose.

PROTOTYPE STATUS (2026-09-21): the harvest stage (sources/edgar_formd.py,
sources/brokercheck.py) cannot reach the open internet from this sandboxed
session - confirmed via curl, WebFetch, and a live `requests` call, all
returning the same organization-policy 403 from the egress proxy (see
/root/.ccr/README.md: "do not retry organization policy denials - report
them instead"). WebSearch (Anthropic-hosted, not subject to this
container's egress policy) still works and can do limited discovery, but
not the structured Form D/BrokerCheck cross-checks the verify.py stage
needs.

What's real and runnable right now, with no network: gp_intake parsing,
scoring.py (validated against ground truth - see validate_ground_truth.py),
compose.py rendering. What's correctly written but untested live: the two
sources/ clients. Run `python -m pa_search.pipeline` once this environment's
network policy allows sec.gov / efts.sec.gov / brokercheck.finra.org (or
run this same code outside this sandbox) to do a real harvest.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path

from pa_search.compose import render_shortlist
from pa_search.gp_intake import load_profile
from pa_search.models import PAFirm, ScoredCandidate
from pa_search.scoring import score_candidate

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR = Path(__file__).parent.parent / "output"


def load_seed_roster(path: str | Path) -> list[PAFirm]:
    firms = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            raw_boutique = (row.get("is_boutique") or "").strip().lower()
            is_boutique = {"true": True, "false": False}.get(raw_boutique)  # None if blank/unrecognized
            firms.append(
                PAFirm(
                    name=row["name"],
                    hq=row["hq"],
                    website=row.get("website") or None,
                    region=row.get("region", ""),
                    is_boutique=is_boutique,
                )
            )
    return firms


def run(gp_profile_path: str, roster_path: str, require_boutique: bool = False) -> str:
    gp = load_profile(gp_profile_path)
    roster = load_seed_roster(roster_path)
    as_of = date.today()

    candidates = []
    skipped_no_network = []
    for firm in roster:
        try:
            # harvest + verify would populate firm.mandates here via
            # sources/edgar_formd.py + verify.py; blocked in this sandbox,
            # see module docstring.
            from pa_search.sources import edgar_formd  # noqa: F401

            skipped_no_network.append(firm.name)
        except Exception:
            skipped_no_network.append(firm.name)

        score = score_candidate(firm, gp, as_of, require_boutique=require_boutique)
        candidates.append(ScoredCandidate(firm=firm, score=score, thesis="(mandate harvest not run - see notes)"))

    candidates.sort(key=lambda c: c.score.total, reverse=True)

    doc = render_shortlist(
        gp=gp,
        candidates=candidates,
        also_considered=[],
        as_of=as_of,
        universe_note=f"{len(roster)}-firm seed roster (no live Form D harvest - network blocked in this session)",
        mandates_traced=0,
    )
    return doc


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gp", default=str(DATA_DIR / "gp_profiles" / "global_bioaccess_fund.json"))
    parser.add_argument("--roster", default=str(DATA_DIR / "pa_roster" / "seed_roster.csv"))
    parser.add_argument("--out", default=str(OUTPUT_DIR / "shortlist.md"))
    args = parser.parse_args()

    result = run(args.gp, args.roster)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(result)
    print(f"Wrote {args.out}")
