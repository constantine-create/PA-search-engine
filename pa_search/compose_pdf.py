"""Client-facing PDF renderer for a placement-agent shortlist.

compose.py's Markdown output is the internal/debug view (raw scores,
verification notes, source URLs, CIK suffixes) - useful for tuning the
pipeline, wrong for anything handed to a GP or prospective client. This
module renders the same underlying ScoredCandidate data as a clean,
Constantine Advisors-branded report: no code, no raw component scores,
no file paths.
"""

from __future__ import annotations

from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import HRFlowable, KeepTogether

from pa_search.models import GPProfile, ScoredCandidate

NAVY = colors.HexColor("#1a2942")
GOLD = colors.HexColor("#b08d57")
SLATE = colors.HexColor("#475569")
LIGHT_RULE = colors.HexColor("#d9dde3")
PAGE_MARGIN = 0.85 * inch


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("FirmName", parent=ss["Heading2"], fontSize=13.5, leading=16,
                           textColor=NAVY, spaceBefore=0, spaceAfter=2))
    ss.add(ParagraphStyle("Meta", parent=ss["Normal"], fontSize=9, leading=12,
                           textColor=SLATE, spaceAfter=6))
    ss.add(ParagraphStyle("Body", parent=ss["Normal"], fontSize=10, leading=14.5,
                           textColor=colors.HexColor("#1f2937"), spaceAfter=6))
    ss.add(ParagraphStyle("Intro", parent=ss["Normal"], fontSize=10.5, leading=15,
                           textColor=colors.HexColor("#1f2937"), spaceAfter=10))
    ss.add(ParagraphStyle("TinyLabel", parent=ss["Normal"], fontSize=7.5, leading=9,
                           textColor=colors.white, alignment=1))
    ss.add(ParagraphStyle("TableHead", parent=ss["Normal"], fontSize=8, leading=10,
                           textColor=colors.white))
    ss.add(ParagraphStyle("TableCell", parent=ss["Normal"], fontSize=8.5, leading=11,
                           textColor=colors.HexColor("#1f2937")))
    ss.add(ParagraphStyle("CoverTitle", parent=ss["Title"], fontSize=26, leading=30,
                           textColor=NAVY, alignment=0, spaceAfter=4))
    ss.add(ParagraphStyle("CoverSub", parent=ss["Normal"], fontSize=14, leading=18,
                           textColor=SLATE, alignment=0, spaceAfter=2))
    ss.add(ParagraphStyle("Kicker", parent=ss["Normal"], fontSize=10, leading=12,
                           textColor=GOLD, alignment=0, spaceAfter=18))
    return ss


def _header_footer(canvas, doc, gp_name: str):
    canvas.saveState()
    canvas.setStrokeColor(LIGHT_RULE)
    canvas.setLineWidth(0.6)
    canvas.line(PAGE_MARGIN, LETTER[1] - 0.55 * inch, LETTER[0] - PAGE_MARGIN, LETTER[1] - 0.55 * inch)
    canvas.setFont("Helvetica-Bold", 8.5)
    canvas.setFillColor(NAVY)
    canvas.drawString(PAGE_MARGIN, LETTER[1] - 0.45 * inch, "CONSTANTINE ADVISORS")
    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(SLATE)
    canvas.drawRightString(LETTER[0] - PAGE_MARGIN, LETTER[1] - 0.45 * inch,
                            f"Placement Agent Shortlist — {gp_name}")

    canvas.line(PAGE_MARGIN, 0.6 * inch, LETTER[0] - PAGE_MARGIN, 0.6 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(SLATE)
    canvas.drawString(PAGE_MARGIN, 0.42 * inch, "Confidential — prepared for internal use and named recipients only")
    canvas.drawRightString(LETTER[0] - PAGE_MARGIN, 0.42 * inch, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def _fit_label(rank: int, total: int) -> tuple[str, colors.Color]:
    frac = rank / max(total, 1)
    if frac <= 1 / 3:
        return "STRONG FIT", NAVY
    if frac <= 2 / 3:
        return "GOOD FIT", GOLD
    return "WORTH A LOOK", SLATE


def _fmt_amount(m) -> str:
    if m.amount_usd_m is None:
        return "—"
    label = " (target)" if m.amount_is_target else ""
    return f"${m.amount_usd_m:,.0f}M{label}"


def _select_mandates(candidate: ScoredCandidate, limit: int = 5):
    mandates = candidate.firm.mandates
    tagged = [m for m in mandates if m.sector_tags]
    tagged.sort(key=lambda m: m.close_or_filing_date or date.min, reverse=True)
    rest = [m for m in mandates if not m.sector_tags]
    rest.sort(key=lambda m: m.close_or_filing_date or date.min, reverse=True)
    return (tagged + rest)[:limit]


def _clean_fund_name(name: str) -> str:
    return name.split("  (CIK")[0].strip()


def _narrative(c: ScoredCandidate) -> str:
    """A clean 1-2 sentence summary built from the underlying data -
    intentionally NOT the internal debug thesis (which references file
    paths and classification methodology - fine for tuning the pipeline,
    wrong for a document going to a client)."""
    mandates = c.firm.mandates
    tagged = [m for m in mandates if m.sector_tags]
    specific = [m for m in mandates if len(m.sector_tags) > 1]
    dated = [m for m in mandates if m.close_or_filing_date]
    latest = max((m.close_or_filing_date for m in dated), default=None)

    bits = []
    if mandates:
        bits.append(f"{len(mandates)} tracked capital-raising mandates on record")
    if tagged:
        bits.append(f"{len(tagged)} directly relevant to this strategy")
    if specific:
        bits.append(f"including {len(specific)} closely matching the fund's specific focus")
    sentence1 = ", ".join(bits) + "." if bits else "Limited public mandate history identified to date."

    sentence2 = ""
    if latest:
        months = (date.today().year - latest.year) * 12 + (date.today().month - latest.month)
        if months <= 12:
            sentence2 = f" Most recent related mandate closed within the past year ({latest.strftime('%B %Y')})."
        elif months <= 30:
            sentence2 = f" Most recent related mandate closed {latest.strftime('%B %Y')}."
        else:
            sentence2 = f" Most recent related mandate on record dates to {latest.strftime('%B %Y')}."

    return sentence1 + sentence2


def render_pdf(
    gp: GPProfile,
    candidates: list[ScoredCandidate],
    out_path: str,
    intro_note: str,
    prepared_by: str = "Constantine Advisors",
    as_of: date | None = None,
) -> None:
    as_of = as_of or date.today()
    ss = _styles()
    story = []

    # --- Cover ---
    story.append(Spacer(1, 1.6 * inch))
    story.append(Paragraph("CONSTANTINE ADVISORS", ParagraphStyle(
        "CoverBrand", fontSize=11, textColor=GOLD, leading=13, spaceAfter=36)))
    story.append(Paragraph("Placement Agent Shortlist", ss["CoverTitle"]))
    story.append(Paragraph(gp.fund_name, ss["CoverSub"]))
    band_lo, band_hi = gp.target_fund_size_usd_m
    band_str = f"${band_lo:,.0f}M" if band_lo == band_hi else f"${band_lo:,.0f}–{band_hi:,.0f}M"
    story.append(Paragraph(f"{band_str} target raise", ParagraphStyle(
        "CoverBand", fontSize=11, textColor=SLATE, spaceBefore=6, spaceAfter=200)))
    story.append(Paragraph(as_of.strftime("%B %d, %Y"), ParagraphStyle(
        "CoverDate", fontSize=10, textColor=SLATE)))
    story.append(Paragraph(f"Prepared by {prepared_by}", ParagraphStyle(
        "CoverPrep", fontSize=10, textColor=SLATE, spaceAfter=4)))
    story.append(Paragraph("Confidential", ParagraphStyle(
        "CoverConf", fontSize=9, textColor=GOLD)))
    story.append(NextPageTemplate("body"))
    story.append(PageBreak())

    # --- Intro / methodology ---
    story.append(Paragraph("Overview", ParagraphStyle("H1", parent=ss["Heading1"], fontSize=15,
                                                        textColor=NAVY, spaceAfter=8)))
    story.append(Paragraph(intro_note, ss["Intro"]))
    story.append(Paragraph(
        f"{len(candidates)} placement agents are profiled below, ordered by fit. Each entry lists "
        f"relevant fund mandates identified through SEC filings and FINRA registration records, "
        f"with sourcing so each claim can be independently verified before outreach.",
        ss["Intro"],
    ))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.75, color=LIGHT_RULE, spaceAfter=14))

    # --- Candidate cards ---
    for i, c in enumerate(candidates, start=1):
        card = []
        label, label_color = _fit_label(i, len(candidates))

        head_table = Table(
            [[
                Paragraph(f"{i}. {c.firm.name}", ss["FirmName"]),
                Table([[Paragraph(label, ss["TinyLabel"])]],
                      colWidths=[1.05 * inch], rowHeights=[0.22 * inch],
                      style=TableStyle([
                          ("BACKGROUND", (0, 0), (-1, -1), label_color),
                          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                          ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                      ])),
            ]],
            colWidths=[4.9 * inch, 1.15 * inch],
        )
        head_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        card.append(head_table)

        meta_bits = [c.firm.hq or "Location on file"]
        if c.firm.website:
            meta_bits.append(c.firm.website)
        if c.firm.is_registered_broker_dealer:
            meta_bits.append("FINRA-registered broker-dealer")
        card.append(Paragraph(" • ".join(meta_bits), ss["Meta"]))

        card.append(Paragraph(_narrative(c), ss["Body"]))

        mandates = _select_mandates(c)
        if mandates:
            rows = [[
                Paragraph("Fund", ss["TableHead"]),
                Paragraph("Size", ss["TableHead"]),
                Paragraph("Date", ss["TableHead"]),
            ]]
            for m in mandates:
                rows.append([
                    Paragraph(_clean_fund_name(m.fund_name), ss["TableCell"]),
                    Paragraph(_fmt_amount(m), ss["TableCell"]),
                    Paragraph(m.close_or_filing_date.strftime("%b %Y") if m.close_or_filing_date else "—",
                              ss["TableCell"]),
                ])
            t = Table(rows, colWidths=[3.9 * inch, 1.15 * inch, 1.0 * inch], repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, NAVY),
                ("LINEBELOW", (0, 1), (-1, -2), 0.4, LIGHT_RULE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f8fa")]),
            ]))
            card.append(Spacer(1, 4))
            card.append(t)

        card.append(Spacer(1, 16))
        story.append(KeepTogether(card))

    doc = BaseDocTemplate(
        out_path, pagesize=LETTER,
        leftMargin=PAGE_MARGIN, rightMargin=PAGE_MARGIN,
        topMargin=0.9 * inch, bottomMargin=0.8 * inch,
        title=f"Placement Agent Shortlist - {gp.fund_name}",
        author=prepared_by,
    )
    cover_frame = Frame(PAGE_MARGIN, 0.8 * inch, LETTER[0] - 2 * PAGE_MARGIN,
                         LETTER[1] - 1.7 * inch, id="cover")
    body_frame = Frame(PAGE_MARGIN, 0.8 * inch, LETTER[0] - 2 * PAGE_MARGIN,
                        LETTER[1] - 1.7 * inch, id="body")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame], onPage=lambda c, d: None),
        PageTemplate(id="body", frames=[body_frame],
                      onPage=lambda c, d: _header_footer(c, d, gp.fund_name)),
    ])
    doc.build(story)
