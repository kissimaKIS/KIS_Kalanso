from decimal import Decimal

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from administration.models import Role
from .models import Classe, PassageDecision, PassageDecisionLine, SchoolYear
from .services.passage import annual_average, doubled_classes, get_or_create_passage, prepare_next_year_from_passage
from common.years import viewed_year


def _director_or_admin(user):
    return user.is_authenticated and (
        user.is_superuser or user.has_admin_role()
        or any(user.has_role(role) for role in (Role.PROMOTER, Role.MANAGER, Role.DIRECTOR))
    )


@login_required
def passage_list(request):
    year = viewed_year()
    classes = Classe.objects.filter(school_year=year).select_related("education_level", "pedagogical_track") if year else Classe.objects.none()
    passages = {p.classe_id: p for p in PassageDecision.objects.filter(source_year=year)} if year else {}
    return render(request, "pedagogie/passage/list.html", {"school_year": year, "classes": classes, "passages": passages})


@login_required
@user_passes_test(_director_or_admin)
def passage_detail(request, classe_id):
    year = viewed_year()
    classe = get_object_or_404(Classe.objects.select_related("education_level", "pedagogical_track", "school", "school_year"), pk=classe_id, school_year=year)
    passage = get_or_create_passage(classe)
    lines = list(passage.lines.select_related("enrollment__student").order_by("enrollment__student__last_name", "enrollment__student__first_name"))
    rows = []
    for line in lines:
        rows.append({
            "line": line,
            "enrollment": line.enrollment,
            "annual_average": annual_average(line.enrollment),
            "doubled": doubled_classes(line.enrollment),
        })
    if request.method == "POST" and passage.status == PassageDecision.Status.PREPARATION:
        for row in rows:
            line = row["line"]
            value = request.POST.get(f"proposal_{line.id}", PassageDecision.Decision.PENDING)
            if value not in dict(PassageDecision.Decision.choices):
                value = PassageDecision.Decision.PENDING
            line.proposal_decision = value
            line.save(update_fields=["proposal_decision", "updated_at"])
        return redirect("passage_detail", classe_id=classe.id)
    return render(request, "pedagogie/passage/detail.html", {"passage": passage, "classe": classe, "rows": rows})


@login_required
@user_passes_test(_director_or_admin)
def passage_cap_decide(request, passage_id):
    passage = get_object_or_404(PassageDecision.objects.select_related("classe__education_level"), pk=passage_id)
    if request.method != "POST":
        return redirect("passage_detail", classe_id=passage.classe_id)
    if passage.status == PassageDecision.Status.DIRECTOR_VALIDATED:
        return redirect("passage_detail", classe_id=passage.classe_id)
    for line in passage.lines.all():
        value = request.POST.get(f"cap_{line.id}", PassageDecision.Decision.PENDING)
        if value not in dict(PassageDecision.Decision.choices):
            value = PassageDecision.Decision.PENDING
        line.cap_decision = value
        line.save(update_fields=["cap_decision", "updated_at"])
    try:
        passage.mark_cap_decided(request.user)
    except ValidationError:
        pass
    return redirect("passage_detail", classe_id=passage.classe_id)


@login_required
@user_passes_test(_director_or_admin)
def passage_director_validate(request, passage_id):
    passage = get_object_or_404(PassageDecision.objects.select_related("classe__education_level"), pk=passage_id)
    if request.method == "POST" and passage.status == PassageDecision.Status.CAP_DECIDED:
        for line in passage.lines.all():
            value = request.POST.get(f"director_{line.id}", PassageDecision.Decision.PENDING)
            if value not in dict(PassageDecision.Decision.choices):
                value = PassageDecision.Decision.PENDING
            line.director_decision = value
            line.observation = request.POST.get(f"observation_{line.id}", "").strip()[:255]
            line.save(update_fields=["director_decision", "observation", "updated_at"])
        try:
            # La validation et la préparation de l'année suivante forment une
            # seule opération : si l'année cible ou son référentiel ne sont
            # pas prêts, rien n'est validé partiellement.
            with transaction.atomic():
                passage.validate_by_director(request.user)
                target_year, created_classes, created_enrollments = prepare_next_year_from_passage(
                    passage, request.user
                )
            messages.success(
                request,
                f"Propositions validées. {len(created_classes)} classe(s) et "
                f"{len(created_enrollments)} inscription(s) préparée(s) pour {target_year.name}."
            )
        except ValidationError as exc:
            messages.error(request, str(exc))
    return redirect("passage_detail", classe_id=passage.classe_id)


def _fmt(value):
    if value is None:
        return ""
    return f"{Decimal(str(value)):.2f}".rstrip("0").rstrip(".").replace(".", ",")


@login_required
@user_passes_test(_director_or_admin)
def passage_print(request, passage_id):
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    passage = get_object_or_404(PassageDecision.objects.select_related("classe__education_level", "classe__school", "source_year"), pk=passage_id)
    if not passage.is_fundamental:
        return HttpResponse("Le document de proposition de passage est réservé à la Fondamentale 1 et 2 pour le moment.", status=400)
    passage = get_or_create_passage(passage.classe)
    school = passage.classe.school
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=10*mm, leftMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm)
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=7.5, leading=9)
    tiny = ParagraphStyle("tiny", parent=styles["Normal"], fontSize=6.5, leading=7.5)
    title = ParagraphStyle("title", parent=styles["Title"], fontSize=14, leading=16, alignment=1, spaceAfter=6*mm)
    story = []
    story.append(Paragraph(school.ministry_name or "MINISTERE DE L’EDUCATION NATIONALE", small))
    story.append(Paragraph(school.academy_name or "", small))
    if passage.is_fundamental:
        story.append(Paragraph(school.cap_name or "", small))
    school_label = school.name
    if school.code:
        school_label = f"{school.name} ({school.code})"
    story.append(Paragraph(school_label, small))
    coordinates = " — ".join(part.strip() for part in (school.address, school.city, f"Tél. : {school.phone}" if school.phone else "", school.email) if part and part.strip())
    if coordinates:
        story.append(Paragraph(coordinates, small))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(f"CLASSE DE : {passage.classe.display_name} &nbsp;&nbsp;&nbsp; Année Scolaire {passage.source_year.name}", small))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph("PROPOSITION DE PASSAGES – REDOUBLEMENTS – EXCLUSIONS", title))

    data = [["N°", "PRENOMS ET NOMS", "Date\nNaiss.", "Date\nEntrée", "N° Mle", "Classe(s)\nDoublée(s)", "Moyenne\nAnnuelle", "Observations"]]
    lines = list(passage.lines.select_related("enrollment__student").order_by("enrollment__student__last_name", "enrollment__student__first_name"))
    for i, line in enumerate(lines, 1):
        st = line.enrollment.student
        doubled = ", ".join(x.classe.display_name for x in doubled_classes(line.enrollment))
        obs = line.observation or line.get_director_decision_display() if line.director_decision != PassageDecision.Decision.PENDING else line.observation
        data.append([f"{i:02d}", f"{st.first_name} {st.last_name}", st.date_of_birth.strftime("%d/%m/%Y") if st.date_of_birth else "", line.enrollment.enrollment_date.strftime("%d/%m/%Y"), st.matricule or "", doubled, _fmt(annual_average(line.enrollment)), obs or ""])
    while len(data) < 21:
        data.append([f"{len(data):02d}", "", "", "", "", "", "", ""])
    table = Table(data, colWidths=[8*mm, 42*mm, 18*mm, 18*mm, 18*mm, 28*mm, 20*mm, 32*mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.35, colors.black), ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 6.5),
        ("LEADING", (0,0), (-1,-1), 7.5), ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (0,0), (0,-1), "CENTER"), ("ALIGN", (6,1), (6,-1), "CENTER"),
    ]))
    story.append(table)
    story.append(Spacer(1, 6*mm))

    def summary(field):
        vals = {"PASSANT":0, "REDOUBLANT":0, "EXCLU":0}
        for line in lines:
            d = getattr(line, field)
            if d in vals:
                vals[d] += 1
        return vals
    labels = [("Passants", "PASSANT"), ("Redoublants", "REDOUBLANT"), ("Exclus", "EXCLU"), ("Total", "TOTAL")]
    prop = summary("proposal_decision")
    cap = summary("cap_decision")
    total_prop = sum(prop.values()); total_cap = sum(cap.values())
    sdata = [["Proposition Conseil", "G", "F", "T"], ["Passants", str(sum(1 for l in lines if l.proposal_decision=="PASSANT" and l.enrollment.student.sex=="M")), str(sum(1 for l in lines if l.proposal_decision=="PASSANT" and l.enrollment.student.sex=="F")), str(prop["PASSANT"])], ["Redoublants", str(sum(1 for l in lines if l.proposal_decision=="REDOUBLANT" and l.enrollment.student.sex=="M")), str(sum(1 for l in lines if l.proposal_decision=="REDOUBLANT" and l.enrollment.student.sex=="F")), str(prop["REDOUBLANT"])], ["Exclus", str(sum(1 for l in lines if l.proposal_decision=="EXCLU" and l.enrollment.student.sex=="M")), str(sum(1 for l in lines if l.proposal_decision=="EXCLU" and l.enrollment.student.sex=="F")), str(prop["EXCLU"])], ["Total", str(sum(1 for l in lines if l.enrollment.student.sex=="M")), str(sum(1 for l in lines if l.enrollment.student.sex=="F")), str(total_prop)]]
    director = summary("director_decision")
    cdata = [["Décision du Directeur du CAP", "G", "F", "T"], ["Passants", str(sum(1 for l in lines if l.director_decision=="PASSANT" and l.enrollment.student.sex=="M")), str(sum(1 for l in lines if l.director_decision=="PASSANT" and l.enrollment.student.sex=="F")), str(director["PASSANT"])], ["Redoublants", str(sum(1 for l in lines if l.director_decision=="REDOUBLANT" and l.enrollment.student.sex=="M")), str(sum(1 for l in lines if l.director_decision=="REDOUBLANT" and l.enrollment.student.sex=="F")), str(director["REDOUBLANT"])], ["Exclus", str(sum(1 for l in lines if l.director_decision=="EXCLU" and l.enrollment.student.sex=="M")), str(sum(1 for l in lines if l.director_decision=="EXCLU" and l.enrollment.student.sex=="F")), str(director["EXCLU"])], ["Total", str(sum(1 for l in lines if l.director_decision and l.director_decision!="PENDING" and l.enrollment.student.sex=="M")), str(sum(1 for l in lines if l.director_decision and l.director_decision!="PENDING" and l.enrollment.student.sex=="F")), str(sum(director.values()))]]
    t1 = Table(sdata, colWidths=[35*mm, 14*mm, 14*mm, 14*mm])
    t2 = Table(cdata, colWidths=[35*mm, 14*mm, 14*mm, 14*mm])
    for t in (t1,t2): t.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.35,colors.black),("BACKGROUND",(0,0),(-1,0),colors.whitesmoke),("FONTSIZE",(0,0),(-1,-1),7),("ALIGN",(1,0),(-1,-1),"CENTER")]))
    story.append(Table([[t1, t2]], colWidths=[77*mm,77*mm]))
    story.append(Spacer(1, 7*mm))
    story.append(Paragraph("Le Maître chargé du cours ____________________&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Le Directeur de l’Ecole ____________________", small))
    story.append(Spacer(1, 7*mm))
    story.append(Paragraph("Koutiala, le ____ / ____ / ______", small))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("Le Directeur du CAP", small))
    story.append(Spacer(1, 10*mm))
    story.append(Paragraph("Signature et cachet", small))
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph(f"État KIS : {passage.get_status_display()}", small))
    if passage.director_validated_by:
        story.append(Paragraph(f"Validée par le Directeur : {passage.director_validated_by.get_full_name() or passage.director_validated_by.username} — {timezone.localtime(passage.director_validated_at):%d/%m/%Y}", small))
    doc.build(story)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="proposition_passage_{passage.classe.display_name.replace(" ", "_")}.pdf"'
    return response
