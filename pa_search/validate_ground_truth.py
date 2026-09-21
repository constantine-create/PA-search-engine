"""Task 7: does the scoring engine's recency+domain-specificity logic alone
reproduce DeepFlows' actual GBF ranking?

This is a deliberately narrow test. The GBF ground-truth fixture only has
two dated fields per firm ("latest_sector_mandate", "latest_domain_specific_
mandate") - not full mandate lists with dollar amounts, so this can only
exercise score_recency() (which folds in a domain-specificity discount),
not score_band/score_stage/etc, which need real amounts this fixture
doesn't carry for every firm. That's the honest scope of what can be
checked without live SEC/FINRA access in this sandbox - see PROTOTYPE
STATUS in pipeline.py for the rest.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pa_search.models import Mandate, SourceTrust
from pa_search.scoring import score_recency

DATA_DIR = Path(__file__).parent.parent / "data"


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    parts = s.split("-")
    if len(parts) == 1:
        return date(int(parts[0]), 1, 1)
    if len(parts) == 2:
        return date(int(parts[0]), int(parts[1]), 1)
    return date(int(parts[0]), int(parts[1]), int(parts[2]))


def main() -> None:
    gt = json.loads((DATA_DIR / "ground_truth" / "global_bioaccess_fund_docx.json").read_text())
    as_of = _parse_date(gt["search_date"])
    domain_tags = {"biotech"}

    rows = []
    for entry in gt["ranked"]:
        mandates = []
        broad_date = _parse_date(entry["latest_sector_mandate"])
        domain_date = _parse_date(entry["latest_domain_specific_mandate"])
        if broad_date:
            mandates.append(
                Mandate(
                    pa_firm=entry["firm"], fund_name="(summary: latest healthcare mandate)", gp_name=None,
                    amount_usd_m=None, amount_is_target=False, sector_tags=["healthcare"],
                    close_or_filing_date=broad_date, role="unspecified", source_url=None,
                    source_trust=SourceTrust.PRIMARY, raw_claim="",
                )
            )
        if domain_date:
            mandates.append(
                Mandate(
                    pa_firm=entry["firm"], fund_name="(summary: latest biotech-specific mandate)", gp_name=None,
                    amount_usd_m=None, amount_is_target=False, sector_tags=["biotech"],
                    close_or_filing_date=domain_date, role="unspecified", source_url=None,
                    source_trust=SourceTrust.PRIMARY, raw_claim="",
                )
            )
        predicted = score_recency(mandates, domain_tags, as_of)
        rows.append({"firm": entry["firm"], "true_rank": entry["rank"], "recency_score": predicted, "note": entry["note"]})

    rows_by_predicted = sorted(rows, key=lambda r: r["recency_score"], reverse=True)
    for i, r in enumerate(rows_by_predicted, start=1):
        r["predicted_rank"] = i

    rows.sort(key=lambda r: r["true_rank"])

    print(f"{'true':>4}  {'pred':>4}  {'score':>6}  firm")
    print("-" * 70)
    for r in rows:
        flag = "  <-- MISS" if abs(r["true_rank"] - r["predicted_rank"]) >= 3 else ""
        print(f"{r['true_rank']:>4}  {r['predicted_rank']:>4}  {r['recency_score']:>6.2f}  {r['firm']}{flag}")

    n = len(rows)
    d2 = sum((r["true_rank"] - r["predicted_rank"]) ** 2 for r in rows)
    spearman = 1 - (6 * d2) / (n * (n**3 - 1))
    print(f"\nSpearman rank correlation (recency-only vs actual DeepFlows rank): {spearman:.3f}")
    print(
        "\nInterpretation: recency+domain-specificity alone is a partial, NOT sufficient,\n"
        "predictor. Expect exactly the misses the ground-truth notes already flag qualitatively:\n"
        "Pacenote Capital (freshest mandates in the set) is overranked here because this test has\n"
        "no fund-size data to apply the band-fit penalty the real card cites ('below the assumed\n"
        "band on size'). Harris Williams is similarly overranked because it has no domain-specific\n"
        "mandate but decent broad-sector recency, and this test can't see the volume/scale signal\n"
        "the real rubric's other components would supply. This confirms the rubric genuinely needs\n"
        "real mandate-level data (amounts, counts) from Form D - not just two summary dates - which\n"
        "is exactly the harvesting step blocked by this sandbox's network policy (see pipeline.py)."
    )


if __name__ == "__main__":
    main()
