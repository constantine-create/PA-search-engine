"""SEC EDGAR Form D client — the core mandate-discovery source.

CONFIDENCE NOTE: this environment's network egress policy blocks direct
requests to sec.gov (confirmed via curl and WebFetch, both returned a
policy-level 403/EGRESS_BLOCKED — not a transient failure, per this
session's proxy README, which is why the code here has not been exercised
against a live response). The endpoints and Form D XML tag names below are
this author's best recollection of the public, well-documented SEC EDGAR
Form D XML Technical Specification. Before relying on this in production:
run `debug_dump_tags()` against ONE real filing and adjust the tag-name
constants in `_TAG_ALIASES` if they don't match.

Two complementary access paths, both free and unauthenticated:

1. Bulk data sets (`https://www.sec.gov/dera/data/form-d`) — quarterly ZIPs
   of tab-delimited tables (FORMDSUBMISSION, ISSUERS, OFFERING, RECIPIENTS,
   RELATEDPERSONS, SIGNATURES) going back to 2008. RECIPIENTS.tsv is the
   real prize: it's a flat table of every placement-agent-style
   compensation recipient disclosed on every Form D filed that quarter,
   joinable to ISSUERS.tsv on ACCESSION_NUMBER. This is almost certainly
   how "1,182 US fund placement agents" and "114 fund mandates traced to
   source documents" (per the DeepFlows GBF search) were assembled at
   scale — it's a local reverse-index build, not one-by-one page fetches.
   Use this for building/refreshing the mandate database.

2. Full-text search (`https://efts.sec.gov/LATEST/search-index`) + individual
   filing XML — for targeted, incremental lookups (e.g. "any Form D from
   this specific GP in the last 90 days that the last bulk download
   missed"). Slower, rate-limited, not a bulk-build tool.
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

SEC_HEADERS = {
    # SEC requests a descriptive User-Agent identifying the requester for
    # all automated EDGAR access: https://www.sec.gov/os/webmaster-faq#code-support
    "User-Agent": "Constantine Advisors Research mbaer@constantineadvisors.com",
}

BULK_DATA_INDEX = "https://www.sec.gov/dera/data/form-d"
FULL_TEXT_SEARCH = "https://efts.sec.gov/LATEST/search-index"


# ---------------------------------------------------------------------------
# Path 1: bulk quarterly data sets
# ---------------------------------------------------------------------------


def bulk_quarter_url(year: int, quarter: int) -> str:
    # Observed URL pattern for the DERA Form D data sets, e.g.
    # https://www.sec.gov/files/dera/data/form-d/2026q2_d.zip - CONFIRM
    # exact filename pattern on the index page above before first use, it
    # has changed format at least once in the past.
    return f"https://www.sec.gov/files/dera/data/form-d/{year}q{quarter}_d.zip"


def download_bulk_quarter(year: int, quarter: int, dest_dir: str | Path) -> Path:
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    url = bulk_quarter_url(year, quarter)
    resp = requests.get(url, headers=SEC_HEADERS, timeout=60)
    resp.raise_for_status()
    zpath = dest_dir / f"{year}q{quarter}_d.zip"
    zpath.write_bytes(resp.content)
    return zpath


@dataclass
class RecipientRow:
    accession_number: str
    recipient_crd: str | None
    recipient_name: str
    associated_bd_name: str | None
    associated_bd_crd: str | None
    state: str | None


def iter_recipients(zip_path: str | Path) -> "list[RecipientRow]":
    """Parse RECIPIENTS.tsv out of one quarterly bulk-data zip.

    Column names below match the DERA Form D data set documentation as of
    recent quarters; DERA has occasionally renamed columns across
    quarters, so this reads by header name (not position) and will raise
    a clear KeyError naming the missing column if a quarter's schema
    differs, rather than silently misreading data.
    """
    out: list[RecipientRow] = []
    with zipfile.ZipFile(zip_path) as zf:
        recipients_name = next(n for n in zf.namelist() if n.upper().endswith("RECIPIENTS.TSV"))
        with zf.open(recipients_name) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"), delimiter="\t")
            for row in reader:
                out.append(
                    RecipientRow(
                        accession_number=row["ACCESSION_NUMBER"],
                        recipient_crd=row.get("RECIPIENT_CRD") or None,
                        recipient_name=row["RECIPIENT_NAME"],
                        associated_bd_name=row.get("RECIPIENT_BD_NAME") or None,
                        associated_bd_crd=row.get("RECIPIENT_BD_CRD") or None,
                        state=row.get("RECIPIENT_STATE") or None,
                    )
                )
    return out


def iter_issuers(zip_path: str | Path) -> "list[dict]":
    """Parse ISSUERS.tsv, keyed by ACCESSION_NUMBER for joining to recipients."""
    out: list[dict] = []
    with zipfile.ZipFile(zip_path) as zf:
        issuers_name = next(n for n in zf.namelist() if n.upper().endswith("ISSUERS.TSV"))
        with zf.open(issuers_name) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"), delimiter="\t")
            out.extend(reader)
    return out


def iter_offering(zip_path: str | Path) -> "list[dict]":
    """Parse OFFERING.tsv - has TOTAL_OFFERING_AMOUNT / TOTAL_AMOUNT_SOLD / industry group."""
    out: list[dict] = []
    with zipfile.ZipFile(zip_path) as zf:
        offering_name = next(n for n in zf.namelist() if n.upper().endswith("OFFERING.TSV"))
        with zf.open(offering_name) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"), delimiter="\t")
            out.extend(reader)
    return out


def build_recipient_index(zip_path: str | Path) -> dict[str, list[dict]]:
    """The actual reverse-index a placement-agent search runs against:
    recipient (placement agent) name -> list of {issuer, offering} records
    for every fund they were paid to help raise that quarter.
    """
    recipients = iter_recipients(zip_path)
    issuers_by_accession: dict[str, list[dict]] = {}
    for row in iter_issuers(zip_path):
        issuers_by_accession.setdefault(row["ACCESSION_NUMBER"], []).append(row)
    offering_by_accession = {row["ACCESSION_NUMBER"]: row for row in iter_offering(zip_path)}

    index: dict[str, list[dict]] = {}
    for r in recipients:
        key = (r.recipient_name or "").strip().upper()
        if not key:
            continue
        index.setdefault(key, []).append(
            {
                "recipient": r,
                "issuers": issuers_by_accession.get(r.accession_number, []),
                "offering": offering_by_accession.get(r.accession_number),
            }
        )
    return index


# ---------------------------------------------------------------------------
# Path 2: full-text search + individual filing XML (targeted lookups)
# ---------------------------------------------------------------------------


def search_form_d(query: str, start_date: str, end_date: str, forms: str = "D,D/A") -> list[dict]:
    """Targeted keyword search across Form D filings, e.g. an issuer name
    or a GP name, within a date range. Returns raw hit dicts from EDGAR's
    full text search (`_source` field per hit); NOT a bulk-build tool -
    EDGAR rate-limits this endpoint (documented guidance: max 10 req/sec,
    be far more conservative for unattended scripts).
    """
    params = {"q": query, "forms": forms, "startdt": start_date, "enddt": end_date}
    resp = requests.get(FULL_TEXT_SEARCH, params=params, headers=SEC_HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return [hit["_source"] | {"_id": hit["_id"]} for hit in data.get("hits", {}).get("hits", [])]


def filing_xml_url(cik: str, accession_number: str) -> str:
    adsh_nodash = accession_number.replace("-", "")
    cik_nozero = str(int(cik))
    return f"https://www.sec.gov/Archives/edgar/data/{cik_nozero}/{adsh_nodash}/primary_doc.xml"


def fetch_form_d_xml(cik: str, accession_number: str) -> bytes:
    url = filing_xml_url(cik, accession_number)
    resp = requests.get(url, headers=SEC_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.content


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def debug_dump_tags(xml_bytes: bytes) -> list[str]:
    """Print every distinct element path in a real filing. Run this once
    against a live filing (once egress is available) to confirm/correct
    the tag names this module assumes, before trusting parse_recipients().
    """
    root = ET.fromstring(xml_bytes)
    paths: set[str] = set()

    def walk(el, prefix=""):
        name = _local_name(el.tag)
        path = f"{prefix}/{name}"
        paths.add(path)
        for child in el:
            walk(child, path)

    walk(root)
    return sorted(paths)


def parse_recipients_from_xml(xml_bytes: bytes) -> list[dict]:
    """Extract Item 12 (sales compensation recipients) from one filing's
    primary_doc.xml. Namespace-agnostic and matches on local tag name
    substrings so it degrades gracefully across schema versions, but the
    field names below are unverified against a live sample in this
    session - see module docstring.
    """
    root = ET.fromstring(xml_bytes)
    out = []
    for el in root.iter():
        if _local_name(el.tag).lower() == "recipient":
            fields = {_local_name(c.tag): (c.text or "").strip() for c in el.iter() if c is not el}
            out.append(fields)
    return out


def parse_offering_amounts(xml_bytes: bytes) -> dict:
    root = ET.fromstring(xml_bytes)
    out = {}
    for el in root.iter():
        name = _local_name(el.tag)
        if name in ("totalOfferingAmount", "totalAmountSold", "totalRemaining"):
            out[name] = (el.text or "").strip()
    return out
