# -*- coding: utf-8 -*-
"""Récapitulatif non officiel des évaluations ponctuelles.

Contexte (retour terrain) : les enseignants saisissent régulièrement des
notes d'interrogations/devoirs via les « évaluations » (Evaluation.nature =
PUNCTUAL), pour leur propre suivi pédagogique. Ces notes n'entrent jamais
dans le bulletin officiel (Bulletin.grades() ne lit que les notes sans
évaluation). Les parents demandaient malgré tout un document simple à leur
remettre pour suivre le travail de leur enfant entre deux bulletins.

Ce module produit ce document : un PDF volontairement différent du bulletin
officiel (pas d'en-tête ministériel, mention « DOCUMENT NON OFFICIEL » bien
visible) afin qu'il ne puisse jamais être confondu avec le bulletin réel.
"""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak,
)
from django.utils.html import escape

from .models import Evaluation, Grade


def _format_note(value):
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".replace(".", ",")


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("PoncSmall", parent=styles["Normal"], fontSize=8.5, leading=10.5))
    styles.add(ParagraphStyle("PoncSchool", parent=styles["Normal"], fontSize=10, leading=12, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(
        "PoncBanner", parent=styles["Normal"], fontSize=10.5, leading=13,
        alignment=1, textColor=colors.HexColor("#8A5A00"), fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "PoncTitle", parent=styles["Title"], fontSize=15, alignment=1,
        spaceAfter=2*mm, textColor=colors.HexColor("#17365D"),
    ))
    styles.add(ParagraphStyle("PoncSubTitle", parent=styles["Normal"], fontSize=9.5, alignment=1, leading=12))
    styles.add(ParagraphStyle("PoncSubjectHeader", parent=styles["Normal"], fontSize=9.5, fontName="Helvetica-Bold", leading=12))
    return styles


def student_ponctuel_context(enrollment, term):
    """Regroupe par matière les notes des évaluations ponctuelles de la période."""
    grades = list(
        Grade.objects.filter(
            enrollment=enrollment, term=term, evaluation__nature=Evaluation.Nature.PUNCTUAL,
        ).select_related("subject", "evaluation").order_by("subject__name", "evaluation__date", "evaluation__id")
    )
    contextual_links = {
        link.subject_id: link for link in enrollment.classe.applicable_subject_links()
    }
    by_subject = {}
    for grade in grades:
        by_subject.setdefault(grade.subject_id, {"subject": grade.subject, "grades": []})
        by_subject[grade.subject_id]["grades"].append(grade)

    subjects = []
    overall_values = []
    for subject_id, data in by_subject.items():
        values = [g.moyenne() for g in data["grades"] if g.composition is not None]
        subject_average = (sum(values) / len(values)) if values else None
        if subject_average is not None:
            overall_values.append(subject_average)
        link = contextual_links.get(subject_id)
        subjects.append({
            "display_name": link.name if link else data["subject"].name,
            "grades": data["grades"],
            "average": subject_average,
        })
    subjects.sort(key=lambda row: row["display_name"])
    overall_average = (sum(overall_values) / len(overall_values)) if overall_values else None
    return {"subjects": subjects, "overall_average": overall_average, "has_data": bool(grades)}


def _student_story(enrollment, term, styles, width):
    school = enrollment.classe.school_year.school
    ctx = student_ponctuel_context(enrollment, term)
    story = []
    story.append(Paragraph(escape(school.name if school else ""), styles["PoncSchool"]))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("DOCUMENT NON OFFICIEL — Ne remplace pas le bulletin", styles["PoncBanner"]))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph("SUIVI DES ÉVALUATIONS PONCTUELLES", styles["PoncTitle"]))
    story.append(Paragraph(
        f"Élève : <b>{escape(str(enrollment.student))}</b> — Classe : {escape(enrollment.classe.display_name)} — "
        f"Période : {escape(term.name)} ({escape(enrollment.classe.school_year.name)})",
        styles["PoncSubTitle"],
    ))
    story.append(Spacer(1, 4*mm))

    if not ctx["has_data"]:
        story.append(Paragraph(
            "Aucune évaluation ponctuelle (interrogation, devoir…) n'a encore été saisie pour cette période.",
            styles["PoncSmall"],
        ))
        return story

    for subject in ctx["subjects"]:
        story.append(Paragraph(escape(subject["display_name"]), styles["PoncSubjectHeader"]))
        data = [["Évaluation", "Date", "Note"]]
        for grade in subject["grades"]:
            data.append([
                escape(grade.evaluation.name) if grade.evaluation else "—",
                grade.evaluation.date.strftime("%d/%m/%Y") if grade.evaluation and grade.evaluation.date else "—",
                _format_note(grade.moyenne() if grade.composition is not None else None),
            ])
        data.append(["", "Moyenne indicative", _format_note(subject["average"])])
        table = Table(data, colWidths=[width*0.55, width*0.22, width*0.23], repeatRows=1)
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#FFF7E6")),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (2, 0), (2, -1), "CENTER"),
        ]))
        story.append(table)
        story.append(Spacer(1, 3*mm))

    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        f"<b>Moyenne indicative toutes matières ponctuelles : {_format_note(ctx['overall_average'])}</b>",
        styles["PoncSmall"],
    ))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(
        "Ce document récapitule les évaluations ponctuelles (interrogations, devoirs…) enregistrées durant la "
        "période à titre de suivi. Il n'a pas de valeur officielle, n'entre pas dans le calcul de la moyenne "
        "générale et ne peut pas remplacer le bulletin officiel de l'établissement.",
        styles["PoncSmall"],
    ))
    return story


def render_ponctuel_pdf(enrollment, term):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=16*mm, leftMargin=16*mm, topMargin=14*mm, bottomMargin=14*mm,
        title="Suivi des évaluations ponctuelles (document non officiel)",
    )
    styles = _styles()
    story = _student_story(enrollment, term, styles, A4[0] - 32*mm)
    doc.build(story)
    return buffer.getvalue()


def render_ponctuel_pdf_classe(enrollments, term):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=16*mm, leftMargin=16*mm, topMargin=14*mm, bottomMargin=14*mm,
        title="Suivi des évaluations ponctuelles (document non officiel)",
    )
    styles = _styles()
    story = []
    for index, enrollment in enumerate(enrollments):
        story += _student_story(enrollment, term, styles, A4[0] - 32*mm)
        if index < len(enrollments) - 1:
            story.append(PageBreak())
    doc.build(story)
    return buffer.getvalue()
