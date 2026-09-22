"""Core data schema for the placement agent search engine.

The shape here is reverse-engineered from two DeepFlows "curated shortlist"
outputs (Global Bioaccess Fund, ISQ InfraTech Growth Fund II) — both the
rendered docx and the underlying score-breakdown view. Field names in
ScoreBreakdown match what was visible in the tool's own UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from enum import Enum
import json


class Freshness(str, Enum):
    FRESH = "FRESH"        # < ~12 months
    RECENT = "RECENT"      # ~1-2 years
    DATED = "DATED"        # ~2-5 years
    NO_DATE = "NO DATE"    # undated / in-market with no close yet


class SourceTrust(str, Enum):
    PRIMARY = "source"          # SEC Form D, FINRA BrokerCheck, Companies House/FCA
    PRESS = "press"              # third-party trade press / news
    AGENT_WEBSITE = "agent website"  # self-reported by the placement agent
    UNVERIFIED = "unverified"     # LLM-drafted claim that didn't confirm against any of the above


@dataclass
class GPProfile:
    """Structured intake from a GP's deck, website, or PPM."""

    fund_name: str
    manager_name: str
    fund_number: str  # e.g. "Fund II"
    strategy_tags: list[str]  # e.g. ["biotech", "medtech"] or ["infrastructure", "physical-world AI"]
    stage_tags: list[str]      # e.g. ["venture", "growth"] or ["early clinical", "mid-late clinical"]
    target_fund_size_usd_m: tuple[float, float]  # (low, high) band, e.g. (200, 250)
    prior_fund_size_usd_m: float | None  # e.g. 80 for Fund I
    geography: list[str]  # target GP/company geography, e.g. ["US", "Global"]
    target_lp_types: list[str]  # e.g. ["family office", "endowment", "fund of funds"]
    source_document: str
    notes: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)


@dataclass
class Mandate:
    """One placement-agent engagement on one fund, as evidenced by one or more sources."""

    pa_firm: str
    fund_name: str
    gp_name: str | None
    amount_usd_m: float | None
    amount_is_target: bool  # True if target/hard-cap rather than confirmed sold
    sector_tags: list[str]
    close_or_filing_date: date | None
    role: str  # "exclusive", "co-agent", "unspecified"
    source_url: str | None
    source_trust: SourceTrust
    raw_claim: str  # the original sentence/snippet this was drafted from
    verification_note: str = ""  # e.g. "Form D/A shows $318M sold vs $325M claimed on site"

    def freshness(self, as_of: date) -> Freshness:
        if self.close_or_filing_date is None:
            return Freshness.NO_DATE
        months = (as_of.year - self.close_or_filing_date.year) * 12 + (
            as_of.month - self.close_or_filing_date.month
        )
        if months <= 12:
            return Freshness.FRESH
        if months <= 24:
            return Freshness.RECENT
        if months <= 60:
            return Freshness.DATED
        return Freshness.DATED


@dataclass
class PAFirm:
    """A placement agent firm — the unit of candidacy in the search."""

    name: str
    hq: str | None
    other_offices: list[str] = field(default_factory=list)
    website: str | None = None
    crd_number: str | None = None  # FINRA (US)
    frn_number: str | None = None  # FCA (UK)
    companies_house_number: str | None = None  # UK
    is_registered_broker_dealer: bool | None = None  # from BrokerCheck/FCA register
    named_contacts: list[str] = field(default_factory=list)  # "Name, Title"
    lp_coverage: list[str] = field(default_factory=list)
    is_boutique: bool | None = None  # vs. bulge-bracket/global platform
    in_preqin: bool | None = None
    region: str = ""  # "United States" / "Europe" / etc.
    mandates: list[Mandate] = field(default_factory=list)


@dataclass
class ScoreBreakdown:
    """Additive rubric — matches the component labels seen in the DeepFlows UI.

    Confirmed against a real example: FocusPoint Private Capital showed
    recency 5 + band 2 + stage 3 + deeptech 2 + lp_fit 0 + emerging 0 +
    evidence 1.0 + boutique 0.5 + us_gp 0 + type 0 = 13.5, matching its
    displayed total exactly. Weight caps below are inferred from the
    handful of examples seen and should be recalibrated as more
    ground-truth searches are collected.
    """

    recency: float = 0.0            # cap 5 — decayed by months since latest in-sector mandate
    band: float = 0.0                # cap 2 — fund-size fit to the GP's target band
    stage: float = 0.0                # cap 3 — venture/growth/buyout stage match
    domain_specificity: float = 0.0    # cap 2 — sector-specific depth (the swappable "biotech"/"deeptech" axis)
    lp_fit: float = 0.0                 # cap 1 — overlap of agent's LP base with GP's target LPs
    emerging: float = 0.0                # cap 1 — emerging-manager / first-fund specialist bonus
    evidence: float = 0.0                 # cap 1.0 — confidence/verification quality of the claims used
    boutique: float = 0.0                  # cap 1 — boutique-vs-platform fit (weighted by search filter)
    us_gp: float = 0.0                      # cap 1 — geography alignment bonus
    type_match: float = 0.0                  # cap 1 — registered placement agent vs. adjacent entity type

    @property
    def total(self) -> float:
        return round(
            self.recency
            + self.band
            + self.stage
            + self.domain_specificity
            + self.lp_fit
            + self.emerging
            + self.evidence
            + self.boutique
            + self.us_gp
            + self.type_match,
            2,
        )


@dataclass
class ScoredCandidate:
    firm: PAFirm
    score: ScoreBreakdown
    thesis: str = ""  # 1-2 sentence fit rationale, LLM-composed from the evidence
    unverified_claims: list[str] = field(default_factory=list)  # "Gemini claimed, not found" style log
