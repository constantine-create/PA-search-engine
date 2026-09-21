"""Additive scoring rubric, component caps calibrated against the two
observed DeepFlows UI examples (FocusPoint Private Capital: 13.5 total,
exact component match; FirstPoint Equity: 15.57 total, components summed
to 14.57 - a ~1pt gap this module doesn't try to explain away).

This is a first-pass calibration from n=2 labeled examples plus the
directional evidence embedded in the GBF ranking (see
data/ground_truth/*.json for the reasoning captured per firm - e.g. why
Pacenote's best-in-set recency still only earned it 9th place, why UBS's
largest-in-set deal size still ranked it last). Treat every weight/decay
constant below as tunable, not ground truth, and recalibrate as more
labeled searches come in.
"""

from __future__ import annotations

from datetime import date

from pa_search.models import GPProfile, Mandate, PAFirm, ScoreBreakdown, SourceTrust


def months_between(d1: date, d2: date) -> int:
    return abs((d2.year - d1.year) * 12 + (d2.month - d1.month))


def _latest(dates: list[date | None]) -> date | None:
    real = [d for d in dates if d is not None]
    return max(real) if real else None


def score_recency(mandates: list[Mandate], domain_tags: set[str], as_of: date, cap: float = 5.0) -> float:
    """Best of: latest domain-specific mandate, latest broad-sector mandate.
    Domain-specific dates count at full weight; broad-sector-only dates are
    discounted, mirroring how GBF's cards track "latest healthcare" and
    "latest biotech-specific" as separate, both-relevant fields.
    """
    domain_dates = [
        m.close_or_filing_date
        for m in mandates
        if m.close_or_filing_date and domain_tags & set(t.lower() for t in m.sector_tags)
    ]
    broad_dates = [m.close_or_filing_date for m in mandates if m.close_or_filing_date]

    best_domain = _latest(domain_dates)
    best_broad = _latest(broad_dates)

    def decay(best: date | None, discount: float) -> float:
        if best is None:
            return 0.0
        m = months_between(best, as_of)
        if m <= 6:
            return cap * discount
        if m <= 12:
            return cap * 0.8 * discount
        if m <= 24:
            return cap * 0.6 * discount
        if m <= 36:
            return cap * 0.4 * discount
        if m <= 60:
            return cap * 0.2 * discount
        return 0.0

    return round(max(decay(best_domain, 1.0), decay(best_broad, 0.7)), 2)


def score_band(mandates: list[Mandate], target_band: tuple[float, float], cap: float = 2.0) -> float:
    """How well the agent's mandate sizes cluster inside the GP's target
    band. Uses the single closest-fitting mandate (an agent needs to have
    done ONE deal at the right size to prove it can, not many)."""
    lo, hi = target_band
    mid = (lo + hi) / 2
    half_width = max((hi - lo) / 2, 1.0)
    sized = [m.amount_usd_m for m in mandates if m.amount_usd_m]
    if not sized:
        return 0.0
    best = min(sized, key=lambda amt: abs(amt - mid))
    if lo <= best <= hi:
        return cap
    distance = min(abs(best - lo), abs(best - hi))
    # linear falloff to 0 at 3x the band's half-width away from the nearest edge
    falloff = max(0.0, 1 - distance / (3 * half_width))
    return round(cap * falloff, 2)


def score_stage(mandates: list[Mandate], gp_stage_tags: set[str], cap: float = 3.0) -> float:
    if not mandates:
        return 0.0
    gp_tags = {t.lower() for t in gp_stage_tags}
    matches = sum(
        1 for m in mandates if gp_tags & {t.lower() for t in m.sector_tags}
    )
    fraction = min(matches / max(len(mandates), 1) * 3, 1.0)  # 3+ matching mandates -> full credit
    return round(cap * fraction, 2)


def score_domain_specificity(mandates: list[Mandate], domain_tags: set[str], cap: float = 2.0) -> float:
    domain_tags_l = {t.lower() for t in domain_tags}
    matches = [m for m in mandates if domain_tags_l & {t.lower() for t in m.sector_tags}]
    if not matches:
        return 0.0
    # 1 domain-specific mandate is a signal; 3+ is a specialist
    return round(cap * min(len(matches) / 3, 1.0), 2)


def score_lp_fit(firm: PAFirm, gp: GPProfile, cap: float = 1.0) -> float:
    if not firm.lp_coverage or not gp.target_lp_types:
        return 0.0
    firm_lps = {t.lower() for t in firm.lp_coverage}
    gp_lps = {t.lower() for t in gp.target_lp_types if "not stated" not in t.lower()}
    if not gp_lps:
        return 0.0
    overlap = len(firm_lps & gp_lps) / len(gp_lps)
    return round(cap * overlap, 2)


def score_emerging(firm: PAFirm, gp: GPProfile, cap: float = 1.0) -> float:
    is_early_fund = gp.fund_number.strip().lower() in {"fund i", "fund ii", "fund 1", "fund 2"}
    specializes = any("emerging" in c.lower() or "first fund" in c.lower() for c in firm.lp_coverage)
    if is_early_fund and specializes:
        return cap
    if is_early_fund:
        return round(cap * 0.3, 2)
    return 0.0


def score_evidence(mandates: list[Mandate], cap: float = 1.0) -> float:
    """Confidence score: fraction of a firm's claimed mandates that are
    backed by primary-source or press evidence rather than left as
    self-reported/unverified. This is meant to reproduce the pattern seen
    on FirstPoint's card (evidence 0.57, i.e. just over half its claims
    were confirmable) vs FocusPoint's (evidence 1.0, everything checked
    out) - see verify.py for where each mandate's source_trust gets set.
    """
    if not mandates:
        return 0.0
    weights = {
        SourceTrust.PRIMARY: 1.0,
        SourceTrust.PRESS: 0.75,
        SourceTrust.AGENT_WEBSITE: 0.4,
        SourceTrust.UNVERIFIED: 0.0,
    }
    avg = sum(weights[m.source_trust] for m in mandates) / len(mandates)
    return round(cap * avg, 2)


def score_boutique(firm: PAFirm, require_boutique: bool, cap: float = 1.0) -> float:
    if firm.is_boutique is None:
        return round(cap * 0.5, 2)  # unknown - GBF's FocusPoint-equivalent showed 0.5 in this situation
    if require_boutique:
        return cap if firm.is_boutique else 0.0
    return round(cap * 0.5, 2)  # boutique-ness isn't being filtered on, so it's a smaller, flat signal


def score_us_gp(firm: PAFirm, gp: GPProfile, cap: float = 1.0) -> float:
    gp_is_us = any("us" in g.lower() or "united states" in g.lower() for g in gp.geography)
    firm_is_us = "united states" in firm.region.lower()
    if gp_is_us and firm_is_us:
        return cap
    return 0.0


def score_type_match(firm: PAFirm, cap: float = 1.0) -> float:
    if firm.is_registered_broker_dealer is True:
        return cap
    if firm.is_registered_broker_dealer is False:
        return 0.0
    return round(cap * 0.5, 2)  # unverified - don't punish as hard as a confirmed non-BD


def score_candidate(
    firm: PAFirm,
    gp: GPProfile,
    as_of: date,
    require_boutique: bool = False,
) -> ScoreBreakdown:
    domain_tags = set(gp.strategy_tags)
    stage_tags = set(gp.stage_tags)
    mandates = firm.mandates

    return ScoreBreakdown(
        recency=score_recency(mandates, domain_tags, as_of),
        band=score_band(mandates, gp.target_fund_size_usd_m),
        stage=score_stage(mandates, stage_tags),
        domain_specificity=score_domain_specificity(mandates, domain_tags),
        lp_fit=score_lp_fit(firm, gp),
        emerging=score_emerging(firm, gp),
        evidence=score_evidence(mandates),
        boutique=score_boutique(firm, require_boutique),
        us_gp=score_us_gp(firm, gp),
        type_match=score_type_match(firm),
    )
