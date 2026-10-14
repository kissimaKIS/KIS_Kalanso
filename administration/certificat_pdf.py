"""Certificat de fréquentation.

Document administratif courant demandé par les parents (bourse, transport,
démarches diverses) attestant qu'un élève est régulièrement inscrit et
fréquente l'établissement au titre de l'année scolaire en cours. Reprend le
même en-tête institutionnel (ministère / académie / CAP / établissement) que
les autres documents officiels déjà générés par l'application (listes
d'élèves, bulletins).
"""
from io import BytesIO
from xml.sax.saxutils import escape

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def _styles():
    styles = getSampleStyleSheet()
    return {
        "header": ParagraphStyle("CertHeader", parent=styles["Normal"], fontSize=8, leading=10, alignment=1),
        "title": ParagraphStyle("CertTitle", parent=styles["Title"], fontSize=15, alignment=1, spaceAfter=6 * mm, spaceBefore=8 * mm),
        "body": ParagraphStyle("CertBody", parent=styles["Normal"], fontSize=11, leading=17),
        "small": ParagraphStyle("CertSmall", parent=styles["Normal"], fontSize=8.5, leading=11),
        "sign": ParagraphStyle("CertSign", parent=styles["Normal"], fontSize=10, alignment=1),
    }


def frequentation_sentence(enrollment):
    """Corps du certificat. Pour une année terminée (clôturée ou non active),
    le texte passe au passé : l'élève *a fréquenté* la classe cette année-là."""
    student = enrollment.student
    school = enrollment.school_year.school
    year = enrollment.school_year
    classe = enrollment.classe
    dob = student.date_of_birth.strftime("%d/%m/%Y") if student.date_of_birth else "……………………"
    pob = escape(student.place_of_birth) if student.place_of_birth else "……………………"
    sex_word = "né" if student.sex == "M" else "née" if student.sex == "F" else "né(e)"
    matricule = escape(student.matricule) if student.matricule else "……………………"
    full_name = f"{student.first_name} {student.last_name}".strip()
    intro = (
        f"Je soussigné(e), Directeur / Directrice de l'établissement <b>{escape(school.name)}</b>, "
        f"certifie que l'élève <b>{escape(full_name)}</b>, {sex_word} le <b>{dob}</b> à <b>{pob}</b>, "
        f"immatriculé(e) sous le numéro <b>{matricule}</b>, "
    )
    if year.is_current:
        return intro + (
            f"est régulièrement inscrit(e) dans notre établissement et fréquente assidûment la classe de "
            f"<b>{escape(classe.display_name)}</b> au titre de l'année scolaire <b>{escape(year.name)}</b>."
        )
    return intro + (
        f"a été régulièrement inscrit(e) dans notre établissement et a fréquenté la classe de "
        f"<b>{escape(classe.display_name)}</b> au titre de l'année scolaire <b>{escape(year.name)}</b> "
        f"(du {year.start_date:%d/%m/%Y} au {year.end_date:%d/%m/%Y})."
    )


def render_certificat_frequentation_pdf(student, enrollment):
    """Génère le PDF du certificat pour un élève et une inscription donnés.

    ``enrollment`` doit correspondre à l'inscription de l'élève pour l'année
    scolaire active (déterminée par l'appelant) — c'est elle qui fournit la
    classe et l'année scolaire mentionnées sur le document.
    """
    school = enrollment.school_year.school
    year = enrollment.school_year
    classe = enrollment.classe

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=22 * mm, leftMargin=22 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
        title="Certificat de fréquentation",
    )
    s = _styles()
    story = []

    story.append(Paragraph(escape(school.ministry_name or "MINISTÈRE DE L'ÉDUCATION NATIONALE"), s["header"]))
    if school.academy_name:
        story.append(Paragraph(escape(school.academy_name), s["header"]))
    if classe.education_level and classe.education_level.school_type in {"fundamental_1", "fundamental_2"} and school.cap_name:
        story.append(Paragraph(escape(school.cap_name), s["header"]))
    story.append(Paragraph(f"<b>{escape(school.name)}</b>" + (f" ({escape(school.code)})" if school.code else ""), s["header"]))
    contact = " — ".join([x for x in [school.address, school.city, f"Tél. : {school.phone}" if school.phone else "", school.email] if x])
    if contact:
        story.append(Paragraph(escape(contact), s["header"]))

    story.append(Spacer(1, 4 * mm))
    story.append(Table([[""]], colWidths=[doc.width], rowHeights=[0.6], style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.7, colors.HexColor("#22406b"))])))
    story.append(Paragraph("CERTIFICAT DE FRÉQUENTATION", s["title"]))

    full_name = f"{student.first_name} {student.last_name}".strip()
    story.append(Paragraph(frequentation_sentence(enrollment), s["body"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "En foi de quoi, le présent certificat est délivré à l'intéressé(e) pour servir et valoir ce que de droit.",
        s["body"],
    ))

    story.append(Spacer(1, 18 * mm))
    today = timezone.localdate().strftime("%d/%m/%Y")
    place = escape(school.city) if school.city else "……………………"
    story.append(Paragraph(f"Fait à {place}, le {today}", s["sign"]))
    story.append(Spacer(1, 14 * mm))
    story.append(Paragraph("Le Directeur / La Directrice", s["sign"]))
    story.append(Spacer(1, 16 * mm))
    story.append(Paragraph("(Signature et cachet de l'établissement)", ParagraphStyle("CertMuted", parent=s["small"], alignment=1)))

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica-Oblique", 8)
        motto = getattr(school, "motto", "")
        if motto:
            canvas.drawCentredString(A4[0] / 2, 10 * mm, motto)
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    safe_name = full_name.replace(" ", "_")
    response["Content-Disposition"] = f'inline; filename="certificat-frequentation-{safe_name}.pdf"'
    return response
