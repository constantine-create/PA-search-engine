"""One-off executive summary PDF explaining the search methodology in
plain language - for sharing with people who want to understand how the
system works, not run it."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
)
from reportlab.platypus.flowables import HRFlowable, KeepTogether

from pa_search.compose_pdf import NAVY, GOLD, SLATE, LIGHT_RULE, PAGE_MARGIN, _styles, _header_footer

OUTPUT_DIR = Path(__file__).parent.parent / "output"

STEPS = [
    ("Read the raise",
     "Extract the fund's strategy, size, geography, and investor type directly from the GP's "
     "own deck and materials - the same starting point a human research associate would use."),
    ("Build the right candidate list",
     "Identify placement agents who actually specialize in that niche - biotech, real estate, "
     "luxury goods, whatever the raise calls for - rather than running every search against one "
     "generic list of firms."),
    ("Pull each firm's real track record",
     "Cross-check candidates against government filings (SEC Form D) and regulatory registration "
     "databases (FINRA BrokerCheck), which legally disclose who was paid to raise which funds. "
     "This is the step that separates verified fact from a firm's own marketing."),
    ("Score for fit",
     "Rank firms on how recent their relevant deals are, how well the deal sizes match, how "
     "specialized they are in the GP's sector, and how well-documented the evidence is."),
    ("Deliver a client-ready report",
     "A plain-language, ranked write-up for each firm - not raw data, not a spreadsheet of scores."),
]


def build(out_path: str) -> None:
    ss = _styles()
    story = []

    story.append(Spacer(1, 1.6 * inch))
    story.append(Paragraph("CONSTANTINE ADVISORS", ParagraphStyle(
        "CoverBrand", fontSize=11, textColor=GOLD, leading=13, spaceAfter=36)))
    story.append(Paragraph("Placement Agent Search", ParagraphStyle(
        "CoverTitle", parent=ss["Title"], fontSize=26, leading=30, textColor=NAVY, alignment=0, spaceAfter=4)))
    story.append(Paragraph("Methodology Summary", ParagraphStyle(
        "CoverSub", fontSize=14, leading=18, textColor=SLATE, alignment=0, spaceAfter=2)))
    story.append(Spacer(1, 200))
    story.append(Paragraph(date.today().strftime("%B %d, %Y"), ParagraphStyle(
        "CoverDate", fontSize=10, textColor=SLATE)))
    story.append(Paragraph("Prepared by Constantine Advisors", ParagraphStyle(
        "CoverPrep", fontSize=10, textColor=SLATE, spaceAfter=4)))
    story.append(Paragraph("Confidential", ParagraphStyle("CoverConf", fontSize=9, textColor=GOLD)))
    story.append(NextPageTemplate("body"))
    story.append(PageBreak())

    def h1(text):
        return Paragraph(text, ParagraphStyle("H1", parent=ss["Heading1"], fontSize=15,
                                               textColor=NAVY, spaceBefore=14, spaceAfter=8))

    story.append(h1("The Goal"))
    story.append(Paragraph(
        "Given a General Partner's fundraising materials, produce a ranked, evidence-backed "
        "shortlist of the placement agents best suited to raise their capital - the kind of "
        "output a specialist research process would produce, generated in a fraction of the time.",
        ss["Intro"]))

    story.append(h1("The Process"))
    for i, (title, body) in enumerate(STEPS, start=1):
        row = Table(
            [[
                Table([[Paragraph(str(i), ParagraphStyle("StepNum", fontSize=12, leading=14,
                                                           textColor=colors.white, alignment=1))]],
                      colWidths=[0.32 * inch], rowHeights=[0.32 * inch],
                      style=TableStyle([
                          ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                          ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                      ])),
                Paragraph(f"<b>{title}</b><br/>{body}", ss["Body"]),
            ]],
            colWidths=[0.45 * inch, 6.0 * inch],
        )
        row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(KeepTogether(row))

    story.append(h1("Beyond SEC Filings: Other Sources We Draw On"))
    story.append(Paragraph(
        "Government filings only exist for US-registered funds. For everything else - a firm's "
        "office locations, named contacts, recent activity, or any fund raised outside the US - "
        "the process pulls from open, public sources on the internet:",
        ss["Intro"]))
    for label, body in [
        ("Firm websites",
         "Fetched directly for team bios, office addresses, and listed contact emails - the "
         "first place to confirm a firm and person are real."),
        ("Trade press and news",
         "Industry publications and press-release wires (e.g. Private Equity International, "
         "PR Newswire, GlobeNewswire) that report fund closes, new mandates, and office openings - "
         "used to confirm a claim independently of the firm's own marketing."),
        ("Professional networks and business intelligence platforms",
         "LinkedIn to confirm someone's actual title and employer; deal-data platforms like "
         "PitchBook, Crunchbase, and RocketReach where accessible, to cross-check a firm's "
         "history and contact details."),
        ("Public business registries",
         "For firms outside the US, official government company registries (e.g. Singapore's "
         "corporate registry) to confirm a firm is a real, currently-registered legal entity."),
        ("General web search",
         "Used to locate the right page or document in the first place, then followed up with a "
         "direct fetch of that specific source rather than trusting the search summary alone."),
    ]:
        story.append(Paragraph(f"<b>{label}</b> — {body}", ss["Body"]))
    story.append(Paragraph(
        "None of these carry the legal weight of a government filing, so the process leans on "
        "corroboration: a claim is only treated as confirmed once it is checked against the "
        "firm's own site and at least one independent source. Anything that can't be corroborated "
        "this way is reported as an unconfirmed lead, not presented as fact - as happened in a "
        "recent search where one contact's stated firm and email were independently confirmed "
        "correct, while a second contact could not be verified and was flagged as such rather "
        "than guessed at.",
        ss["Body"]))

    story.append(h1("Why This Is More Rigorous Than a Standard Search"))
    story.append(Paragraph(
        "Every claim about a firm's track record is checked against a primary source wherever "
        "one exists - an actual government filing, not just the firm's own website or marketing. "
        "Before using the process live, we tested it against a real, known outcome and confirmed "
        "it independently reproduced the correct ranking with strong accuracy.",
        ss["Intro"]))

    story.append(h1("Current Status"))
    story.append(Paragraph(
        "This is an active build, not a finished product. Two things worth knowing:",
        ss["Intro"]))
    for bullet in [
        "It is strongest for US-based funds, where SEC filings exist to verify claims against. "
        "For funds outside the US, or ones raising from family offices rather than institutions, "
        "the process relies more on general web research, which is inherently less rigorous.",
        "One of the two verification data sources (SEC EDGAR) is intermittently blocked by a "
        "technical/network issue outside our control, which we are working to resolve.",
    ]:
        story.append(Paragraph(f"• {bullet}", ss["Body"]))

    doc = BaseDocTemplate(
        out_path, pagesize=LETTER,
        leftMargin=PAGE_MARGIN, rightMargin=PAGE_MARGIN,
        topMargin=0.9 * inch, bottomMargin=0.8 * inch,
        title="Placement Agent Search - Methodology Summary", author="Constantine Advisors",
    )
    cover_frame = Frame(PAGE_MARGIN, 0.8 * inch, LETTER[0] - 2 * PAGE_MARGIN,
                         LETTER[1] - 1.7 * inch, id="cover")
    body_frame = Frame(PAGE_MARGIN, 0.8 * inch, LETTER[0] - 2 * PAGE_MARGIN,
                        LETTER[1] - 1.7 * inch, id="body")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame], onPage=lambda c, d: None),
        PageTemplate(id="body", frames=[body_frame],
                      onPage=lambda c, d: _header_footer(c, d, "Methodology Summary")),
    ])
    doc.build(story)


if __name__ == "__main__":
    out_path = OUTPUT_DIR / "Constantine_Advisors_Placement_Agent_Search_Methodology.pdf"
    build(str(out_path))
    print(f"Wrote {out_path}")
