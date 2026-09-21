"""Stage 5: draft -> verify -> flag.

This is the piece that separates a trustworthy shortlist from a plausible-
sounding one. An LLM drafts a claim from an unstructured source (agent
website, press release); this module tries to match it against a primary-
source record (an SEC Form D recipient, ideally) and either confirms it,
downgrades its trust level, or leaves it explicitly logged as unconfirmed -
mirroring the "Gemini claimed, not found: ..." audit trail visible on the
FirstPoint Equity card in the ISQ ground truth.

Never silently drop an unconfirmed claim and never silently "correct" a
claimed figure to match a primary source without recording that a
discrepancy existed - both destroy the auditability that makes the output
usable in front of a GP.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher

from pa_search.models import Mandate, SourceTrust


@dataclass
class ClaimedMandate:
    """What an LLM drafted after reading an agent's website or a press
    article, before any cross-check."""

    pa_firm: str
    fund_name: str
    gp_name: str | None
    amount_usd_m: float | None
    amount_is_target: bool
    sector_tags: list[str]
    claimed_date: date | None
    role: str
    source_url: str
    source_type: SourceTrust  # PRESS or AGENT_WEBSITE only at this stage
    raw_text: str


def _name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def find_best_formd_match(claim: ClaimedMandate, formd_records: list[dict], threshold: float = 0.72) -> dict | None:
    """formd_records: output of edgar_formd.build_recipient_index()[claim.pa_firm],
    i.e. a list of {"recipient": RecipientRow, "issuers": [...], "offering": {...}}.
    """
    best = None
    best_score = 0.0
    for rec in formd_records:
        for issuer in rec.get("issuers", []):
            name = issuer.get("ISSUER_NAME", "")
            score = _name_similarity(claim.fund_name, name)
            if score > best_score:
                best_score = score
                best = rec
    return best if best_score >= threshold else None


def _parse_amount(offering: dict | None, key: str) -> float | None:
    if not offering:
        return None
    raw = offering.get(key)
    if not raw:
        return None
    try:
        return float(raw) / 1_000_000
    except ValueError:
        return None


def verify_claim(claim: ClaimedMandate, formd_records: list[dict]) -> Mandate:
    match = find_best_formd_match(claim, formd_records)

    if match is None:
        return Mandate(
            pa_firm=claim.pa_firm,
            fund_name=claim.fund_name,
            gp_name=claim.gp_name,
            amount_usd_m=claim.amount_usd_m,
            amount_is_target=claim.amount_is_target,
            sector_tags=claim.sector_tags,
            close_or_filing_date=claim.claimed_date,
            role=claim.role,
            source_url=claim.source_url,
            source_trust=claim.source_type,
            raw_claim=claim.raw_text,
            verification_note="no matching SEC Form D recipient record found - claim not independently confirmed",
        )

    notes = []
    formd_amount = _parse_amount(match.get("offering"), "TOTAL_AMOUNT_SOLD")
    if claim.amount_usd_m and formd_amount and abs(claim.amount_usd_m - formd_amount) > max(1.0, 0.05 * formd_amount):
        notes.append(f"claimed ${claim.amount_usd_m:.0f}M vs Form D total amount sold ${formd_amount:.0f}M")

    recipient = match["recipient"]
    if recipient.associated_bd_name and recipient.associated_bd_name.lower() != claim.pa_firm.lower():
        notes.append(
            f"Form D lists associated broker-dealer as {recipient.associated_bd_name!r}, "
            f"not {claim.pa_firm!r} directly - confirm the relationship"
        )

    return Mandate(
        pa_firm=claim.pa_firm,
        fund_name=claim.fund_name,
        gp_name=claim.gp_name,
        amount_usd_m=formd_amount or claim.amount_usd_m,
        amount_is_target=False if formd_amount else claim.amount_is_target,
        sector_tags=claim.sector_tags,
        close_or_filing_date=claim.claimed_date,
        role=claim.role,
        source_url=claim.source_url,
        source_trust=SourceTrust.PRIMARY,
        raw_claim=claim.raw_text,
        verification_note="; ".join(notes) if notes else "confirmed against SEC Form D recipient record",
    )
