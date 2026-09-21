"""Stage 1: turn a GP deck/website into a structured GPProfile.

Text extraction here is mechanical (pdfminer). Turning that text into the
structured GPProfile fields is an LLM step, not a deterministic parse — deck
layouts vary too much (see GBF's narrative slides vs. ISQ's plain website).
`EXTRACTION_PROMPT` is the prompt used to drive that step; run it through
Claude (or another LLM) with the extracted text and hand the JSON result to
`GPProfile(**json.loads(result))`.
"""

from __future__ import annotations

import json
from pathlib import Path

from pa_search.models import GPProfile


def extract_text_from_pdf(path: str | Path) -> str:
    from pdfminer.high_level import extract_text

    return extract_text(str(path))


EXTRACTION_PROMPT = """\
You are extracting a structured fundraising profile from a GP's own materials
(deck text or website copy) for placement-agent matching purposes.

Return ONLY a JSON object with these keys, matching this schema:
- fund_name: str — the fund's marketing name
- manager_name: str — the management company / GP entity name
- fund_number: str — e.g. "Fund I", "Fund II"
- strategy_tags: list[str] — sector/strategy keywords (e.g. "biotech", "medtech",
  "infrastructure", "physical-world AI"); use the GP's own vocabulary first,
  then add standard category terms a placement agent's track record would be
  tagged with
- stage_tags: list[str] — investment stage focus (e.g. "early clinical",
  "growth", "buyout", "pre-seed")
- target_fund_size_usd_m: [low, high] — the CURRENT fundraise target band in
  $M. If the deck states one number, use [number, number]. Flag in `notes`
  if a size figure appears in more than one place and they disagree — do not
  silently pick one.
- prior_fund_size_usd_m: number or null — the prior fund's size, if this is
  not a debut fund
- geography: list[str] — target investment geography
- target_lp_types: list[str] — LP types explicitly targeted or implied
  (family office, endowment, foundation, fund of funds, pension, sovereign,
  RIA/OCIO, consultant-gatekeeper)
- source_document: str — filename or URL this was extracted from
- notes: str — anything a human reviewer should double check (ambiguous
  figures, conflicting dates, multiple size figures found in different
  places)

Extracted text follows between triple quotes.
\"\"\"{text}\"\"\"
"""


def save_profile(profile: GPProfile, path: str | Path) -> None:
    Path(path).write_text(profile.to_json())


def load_profile(path: str | Path) -> GPProfile:
    data = json.loads(Path(path).read_text())
    data["target_fund_size_usd_m"] = tuple(data["target_fund_size_usd_m"])
    return GPProfile(**data)
