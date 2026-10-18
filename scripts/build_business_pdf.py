"""Generate me/about_business.pdf — the full (fictional) SunCedar Energy business profile.

Run from the project root:  python scripts/build_business_pdf.py
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT = Path(__file__).resolve().parent.parent / "me" / "about_business.pdf"

BRAND = colors.HexColor("#C2410C")  # sunset orange
INK = colors.HexColor("#1F2937")

styles = getSampleStyleSheet()
TITLE = ParagraphStyle("T", parent=styles["Title"], textColor=BRAND, fontSize=26, spaceAfter=4)
TAGLINE = ParagraphStyle("TL", parent=styles["Normal"], alignment=TA_CENTER, fontSize=12,
                         textColor=INK, spaceAfter=4, fontName="Helvetica-Oblique")
H1 = ParagraphStyle("H1", parent=styles["Heading2"], textColor=BRAND, spaceBefore=12, spaceAfter=4)
H2 = ParagraphStyle("H2", parent=styles["Heading3"], textColor=INK, spaceBefore=6, spaceAfter=2)
BODY = ParagraphStyle("B", parent=styles["BodyText"], fontSize=10, leading=14, textColor=INK)
SMALL = ParagraphStyle("S", parent=BODY, fontSize=8, leading=10, textColor=colors.grey)
CELL = ParagraphStyle("C", parent=BODY, fontSize=9, leading=11)


def p(text, style=BODY):
    return Paragraph(text, style)


def bullets(items):
    return ListFlowable(
        [ListItem(p(i), leftIndent=12, value="•") for i in items],
        bulletType="bullet", start="•", leftIndent=12,
    )


def table(rows, widths):
    data = [[p(f"<b>{c}</b>", CELL) for c in rows[0]]] + [[p(c, CELL) for c in r] for r in rows[1:]]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FFEDD5")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


story = [
    p("SunCedar Energy", TITLE),
    p("Clean power that never sleeps.", TAGLINE),
    p("Business Profile &middot; Beirut, Lebanon &middot; Founded 2021", ParagraphStyle(
        "c", parent=SMALL, alignment=TA_CENTER)),
    Spacer(1, 10),

    p("1. Company Overview", H1),
    p("SunCedar Energy is a Lebanese solar-energy company that designs, installs and maintains solar "
      "and battery systems for homes and small businesses. It was founded in 2021 in Beirut by "
      "Rania Haddad and Karim Aoun, after years of daily power cuts convinced them that families "
      "should not have to depend on noisy, polluting diesel generators. Since then the company has "
      "installed more than 1,200 systems, employs 38 people, and holds an average customer rating of "
      "4.8 out of 5 from more than 900 reviews."),

    p("2. Mission and Vision", H1),
    p("<b>Mission:</b> to give every home and small business in Lebanon clean, reliable, "
      "around-the-clock electricity, and freedom from diesel generators."),
    p("<b>Vision:</b> a quieter, cleaner Lebanon powered by the sun by 2035."),

    p("3. Services and Pricing", H1),
    p("All prices are in US dollars, include equipment, mounting structure, installation, SunPulse "
      "app setup and the first year of the CareShield maintenance plan. Roof works beyond standard "
      "mounting (for example elevated pergola structures) are quoted separately after the audit."),

    p("3.1 Free Energy Audit", H2),
    p("A 60-minute on-site visit by a SunCedar engineer: load assessment, roof and shading survey, "
      "and a tailored written proposal delivered within 48 hours. The audit is free and without "
      "obligation anywhere in our service area."),

    p("3.2 Home Solar Packages", H2),
    table([
        ["Package", "System", "Best for", "Price"],
        ["Essential", "3 kWp solar panels, 5 kWh LiFePO4 battery, 5 kW hybrid inverter",
         "Apartments: lights, fridge, internet, TV and laptops", "$3,900"],
        ["Comfort", "5 kWp solar panels, 10 kWh LiFePO4 battery, 8 kW hybrid inverter",
         "Families: adds washing machine, water pump and one AC unit during the day", "$6,500"],
        ["Premium", "8 kWp solar panels, 15 kWh LiFePO4 battery, 10 kW hybrid inverter",
         "Villas and large homes: whole house including 2-3 AC units during the day", "$9,800"],
    ], [2.0 * cm, 6.0 * cm, 6.2 * cm, 1.6 * cm]),
    Spacer(1, 4),
    p("Every package is designed to be expandable: panels and batteries can be added later."),

    p("3.3 Business Solar", H2),
    p("Custom systems from 10 kWp to 100 kWp for shops, clinics, restaurants, schools and small "
      "factories. Pricing is by custom quote after the free energy audit. Typical payback compared "
      "with diesel generation is 2 to 4 years."),

    p("3.4 Battery Retrofit", H2),
    p("Adds LiFePO4 battery storage to an existing solar system, subject to a compatibility check of "
      "the existing inverter. Starts from $1,800 for 5 kWh of storage."),

    p("3.5 CareShield Maintenance Plan", H2),
    p("$15 per month or $150 per year (the first year is included with every package). Includes two "
      "professional panel cleanings per year, an annual system health check, 24/7 remote monitoring, "
      "priority repairs within 48 hours, and a 10% discount on replacement parts."),

    p("3.6 SunPulse Monitoring App", H2),
    p("Free with every installation, for iOS and Android. Shows live solar production and battery "
      "level, sends outage and fault alerts, and produces a monthly savings report."),

    p("3.7 What We Do Not Offer", H2),
    p("We do not currently install solar water heaters or electric-vehicle chargers, and we do not "
      "sell equipment without installation."),

    p("4. Payment and Financing", H1),
    bullets([
        "Payment schedule: 30% deposit at contract signing, 60% when equipment is delivered, and 10% "
        "after commissioning.",
        "Accepted methods: bank transfer, cash (USD) and credit/debit card.",
        "Financing: 12-month interest-free installments on the Essential and Comfort packages through "
        "our partner, Cedar Community Bank, subject to the bank's approval.",
    ]),

    p("5. Warranties", H1),
    bullets([
        "Solar panels: 25-year performance warranty (at least 80% of rated output).",
        "Inverters: 10 years.",
        "Batteries: 10 years or 6,000 cycles, whichever comes first.",
        "Workmanship (installation): 5 years.",
    ]),

    p("6. Installation Process and Timeline", H1),
    bullets([
        "Step 1 - Book a free energy audit (phone, WhatsApp, email or this assistant).",
        "Step 2 - On-site audit; written proposal within 48 hours.",
        "Step 3 - Sign the contract and pay the 30% deposit.",
        "Step 4 - Installation: 1-2 days for a residential system.",
        "Step 5 - Commissioning, SunPulse app setup and a hand-over walkthrough.",
    ]),
    p("From audit to switch-on typically takes 7 to 14 days for a home system."),

    p("7. Service Area, Hours and Contact", H1),
    bullets([
        "Service area: Greater Beirut, Mount Lebanon, Byblos (Jbeil) and Batroun. Projects outside "
        "these areas are considered case by case.",
        "Showroom: 2nd floor, 14 Makdessi Street, Hamra, Beirut.",
        "Opening hours: Monday-Friday 8:00-18:00, Saturday 9:00-14:00, closed Sunday.",
        "24/7 emergency support line for CareShield members.",
        "Email: hello@suncedar-energy.example &middot; Phone and WhatsApp: +961 1 555 0123.",
    ]),

    p("8. Our Team", H1),
    p("<b>Rania Haddad - Co-founder and CEO.</b> Electrical engineer with 12 years of experience in "
      "power-grid planning. Leads company strategy and partnerships."),
    p("<b>Karim Aoun - Co-founder and CTO.</b> Power-electronics engineer who designed the SunPulse "
      "monitoring platform and leads system design."),
    p("<b>Maya Saliba - Head of Customer Success.</b> Runs the customer support team and the "
      "CareShield maintenance program."),
    p("<b>Elie Nassar - Lead Installation Engineer.</b> Supervises our six installation crews and is "
      "certified in high-voltage battery safety."),

    p("9. Our Unique Value Proposition", H1),
    p("<b>Outage-proof in two weeks, with one accountable team.</b>"),
    bullets([
        "One team from audit to after-sales: no subcontractors, no finger-pointing.",
        "Transparent, fixed package pricing published up front.",
        "LiFePO4-only batteries: safer and longer-lasting than lead-acid.",
        "SunPulse live monitoring with outage alerts and monthly savings reports.",
        "A 48-hour repair promise for CareShield members.",
    ]),

    p("10. Frequently Asked Questions", H1),
    p("<b>Does the system keep working during a power cut?</b> Yes. The hybrid inverter switches to "
      "solar and battery power automatically in under 10 milliseconds, so most devices do not notice."),
    p("<b>Can I expand my system later?</b> Yes. All packages are designed so panels and batteries "
      "can be added later."),
    p("<b>I live in an apartment building. Can I still install solar?</b> Yes, with roof-access "
      "permission from the building committee. We help prepare the documentation."),
    Spacer(1, 14),
    p("SunCedar Energy is a fictional company created for the EECE 503P/798S Agentic Systems course "
      "assignment. All names, numbers and contact details are invented.", SMALL),
]


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title="SunCedar Energy - Business Profile", author="SunCedar Energy")
    doc.build(story)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
