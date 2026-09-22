"""Stage 6: render a ranked candidate list as Markdown, matching the card
structure observed in both ground-truth docx outputs (GBF and ISQ).

Markdown here, not docx directly - it's the readable intermediate for
reviewing/tuning the pipeline. Converting a finished run to the house-style
.docx is a formatting pass on top of this, not part of the search logic.
"""

from __future__ import annotations

from datetime import date

from pa_search.models import GPProfile, Mandate, ScoredCandidate


def _fmt_amount(m: Mandate) -> str:
    if m.amount_usd_m is None:
        return "amount n/d"
    label = "target" if m.amount_is_target else "sold"
    return f"${m.amount_usd_m:.0f}M {label}"


def _fmt_mandate_line(m: Mandate, as_of: date) -> str:
    freshness = m.freshness(as_of).value
    date_str = m.close_or_filing_date.isoformat() if m.close_or_filing_date else "no date"
    sectors = ", ".join(m.sector_tags) if m.sector_tags else ""
    src = f"[{m.source_trust.value}]({m.source_url})" if m.source_url else f"[{m.source_trust.value}]"
    line = f"- **{m.fund_name}** · {_fmt_amount(m)} · {sectors} · {date_str} `{freshness}` {src}"
    if m.verification_note:
        line += f"\n  - _verification: {m.verification_note}_"
    return line


def render_candidate_card(rank: int, candidate: ScoredCandidate, as_of: date) -> str:
    f = candidate.firm
    offices = ", ".join(f.other_offices) if f.other_offices else ""
    contacts = "; ".join(f.named_contacts) if f.named_contacts else ""
    header = f"### {rank}. {f.name}\n"
    location = (f.hq or "Location not confirmed") + (f" ({offices})" if offices else "")
    meta_bits = [location]
    if contacts:
        meta_bits.append(contacts)
    if f.website:
        meta_bits.append(f"[Website]({f.website})")
    if f.crd_number:
        meta_bits.append(f"FINRA CRD {f.crd_number}")
    if f.frn_number:
        meta_bits.append(f"FCA FRN {f.frn_number}")
    meta = " · ".join(meta_bits)

    lines = [header, meta, "", candidate.thesis or "", ""]
    lines.append(f"**Score: {candidate.score.total}** "
                 f"(recency {candidate.score.recency} · band {candidate.score.band} · "
                 f"stage {candidate.score.stage} · domain {candidate.score.domain_specificity} · "
                 f"lp_fit {candidate.score.lp_fit} · emerging {candidate.score.emerging} · "
                 f"evidence {candidate.score.evidence} · boutique {candidate.score.boutique} · "
                 f"us_gp {candidate.score.us_gp} · type {candidate.score.type_match})")
    lines.append("")

    sorted_mandates = sorted(
        f.mandates, key=lambda m: m.close_or_filing_date or date.min, reverse=True
    )
    lines.append("Mandates on record:")
    for m in sorted_mandates:
        lines.append(_fmt_mandate_line(m, as_of))

    if candidate.unverified_claims:
        lines.append("")
        lines.append("_Claimed but not independently confirmed:_")
        for c in candidate.unverified_claims:
            lines.append(f"- {c}")

    if f.lp_coverage:
        lines.append("")
        lines.append(f"LP coverage: {', '.join(f.lp_coverage)}")
    lines.append(f"Region: {f.region}")

    return "\n".join(lines)


def render_shortlist(
    gp: GPProfile,
    candidates: list[ScoredCandidate],
    also_considered: list[dict],
    as_of: date,
    universe_note: str,
    mandates_traced: int,
) -> str:
    band_lo, band_hi = gp.target_fund_size_usd_m
    title = f"Curated shortlist · {as_of.isoformat()}"
    subtitle = f"Placement agents for {gp.fund_name}"
    intro = (
        f"{len(candidates)} placement agents fit to a ${band_lo:.0f}-{band_hi:.0f}M "
        f"{'/'.join(gp.strategy_tags[:2])} raise, ordered by fit (evidence score)."
    )
    methodology = (
        f"Screened via {universe_note}; traced {mandates_traced} fund mandates to source documents; "
        f"scored each firm on recency of its last in-sector mandate, sector specificity, "
        f"mandate volume, and size-band fit."
    )

    parts = [f"# {subtitle}", "", title, "", intro, "", methodology, ""]

    for i, c in enumerate(candidates, start=1):
        parts.append(render_candidate_card(i, c, as_of))
        parts.append("")

    if also_considered:
        parts.append("## Also considered")
        for item in also_considered:
            parts.append(f"- **{item['firm']}** — {item['note']}")
        parts.append("")

    parts.append(
        "---\n_Confirm registration and current mandates before engaging. "
        "Sources are as published by the GPs, agents, SEC filings and press cited; "
        "dates are close or filing dates._"
    )
    return "\n".join(parts)
