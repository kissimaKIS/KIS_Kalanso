from django.db import transaction
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse
from django.urls import reverse
from django.db.models import Count, Q
from django.utils import timezone
from xml.sax.saxutils import escape
from administration.models import SchoolYear, Teacher, OtherPersonnel
from pedagogie.models import Classe, Enrollment
from .models import Attendance, DisciplineIncident, TeacherAttendance, OtherPersonnelAttendance
from .forms import AttendanceForm, DisciplineIncidentForm, DisciplineEntryForm
from common.pagination import paginate
from common.years import viewed_year


@login_required
def attendance_list(request):
    """Écran unique de saisie et de consultation des présences élèves.

    La classe et la date sont choisies ici. La saisie est enregistrée sur la
    même page afin que l'utilisateur puisse corriger ou compléter les
    présences sans naviguer vers une autre page.
    """
    year = viewed_year()
    classes = (
        Classe.objects.filter(school_year=year)
        .select_related("education_level")
        .order_by("education_level__order", "name")
        if year else Classe.objects.none()
    )

    selected_class_id = request.POST.get("classe") or request.GET.get("classe") or ""
    selected_date_raw = request.POST.get("date") or request.GET.get("date") or ""
    selected_date = timezone.localdate()
    if selected_date_raw:
        try:
            from datetime import date as date_cls
            selected_date = date_cls.fromisoformat(selected_date_raw)
        except (TypeError, ValueError):
            messages.error(request, "La date sélectionnée est invalide.")

    selected_class = None
    enrollments = Enrollment.objects.none()
    attendance_map = {}
    draft_attendance_map = {}

    if year and selected_class_id:
        selected_class = get_object_or_404(classes, pk=selected_class_id)
        enrollments = (
            Enrollment.objects.filter(classe=selected_class, school_year=year)
            .select_related("student")
            .order_by("student__last_name", "student__first_name")
        )
        existing = Attendance.objects.filter(
            enrollment__in=enrollments, date=selected_date
        )
        attendance_map = {record.enrollment_id: record for record in existing}

        if request.method == "POST":
            # Une classe ne peut être enregistrée qu'une seule fois pour une
            # date donnée. Toute nouvelle tentative est refusée côté serveur.
            if attendance_map:
                messages.error(
                    request,
                    "Les présences de cette classe et de cette date sont déjà enregistrées et ne peuvent plus être modifiées.",
                )
            else:
                year_start = year.start_date
                year_end = year.end_date
                if (year_start and selected_date < year_start) or (year_end and selected_date > year_end):
                    messages.error(request, "La date doit appartenir à l'année scolaire active.")
                else:
                    errors = []
                    allowed_statuses = {choice[0] for choice in Attendance.STATUS_CHOICES}
                    entries = []
                    for enrollment in enrollments:
                        status = request.POST.get(f"status_{enrollment.id}", "PRESENT")
                        if status not in allowed_statuses:
                            status = "PRESENT"
                        note = request.POST.get(f"note_{enrollment.id}", "").strip()
                        justification_note = request.POST.get(
                            f"justification_note_{enrollment.id}", ""
                        ).strip()
                        justified = request.POST.get(f"justified_{enrollment.id}") == "on"
                        raw_minutes = request.POST.get(f"late_minutes_{enrollment.id}", "").strip()
                        late_minutes = (
                            int(raw_minutes)
                            if raw_minutes.isdigit() and int(raw_minutes) > 0
                            else None
                        )
                        # Conserver systématiquement les valeurs saisies, y compris
                        # pour une ligne invalide. Ainsi, si une seule ligne contient
                        # une erreur (ex. retard sans durée), aucune des autres saisies
                        # et aucune valeur de cette ligne ne disparaît du tableau.
                        draft_attendance_map[enrollment.id] = {
                            "status": status,
                            "is_justified": justified if status in {"ABSENT", "LATE"} else False,
                            "justification_note": justification_note if status in {"ABSENT", "LATE"} else "",
                            "late_minutes": raw_minutes,
                            "note": note,
                        }
                        if status == "LATE" and late_minutes is None:
                            errors.append(f"{enrollment.student} : indiquez la durée de retard.")
                            continue
                        entries.append({
                            "enrollment": enrollment,
                            "status": status,
                            "is_justified": justified if status in {"ABSENT", "LATE"} else False,
                            "justification_note": justification_note if status in {"ABSENT", "LATE"} else "",
                            "late_minutes": late_minutes if status == "LATE" else None,
                            "note": note,
                        })
                    if errors:
                        for error in errors:
                            messages.error(request, error)
                    else:
                        with transaction.atomic():
                            for entry in entries:
                                Attendance.objects.create(
                                    enrollment=entry["enrollment"],
                                    date=selected_date,
                                    status=entry["status"],
                                    is_justified=entry["is_justified"],
                                    justification_note=entry["justification_note"],
                                    late_minutes=entry["late_minutes"],
                                    note=entry["note"],
                                    recorded_by=request.user,
                                )
                        messages.success(
                            request,
                            "Présences enregistrées. Elles sont désormais consultables en lecture seule.",
                        )
                        existing = Attendance.objects.filter(
                            enrollment__in=enrollments, date=selected_date
                        )
                        attendance_map = {record.enrollment_id: record for record in existing}


    records = (
        Attendance.objects.filter(enrollment__school_year=year)
        .select_related(
            "enrollment__student", "enrollment__classe__education_level",
            "enrollment__classe__pedagogical_track",
        )
        if year else Attendance.objects.none()
    )
    history_date = request.GET.get("historique_date")
    if history_date:
        records = records.filter(date=history_date)
    if selected_class_id:
        records = records.filter(enrollment__classe_id=selected_class_id)

    # Historique paginé par date : on ne charge que les journées de la page
    # (5 dates), jamais toute l'année (des dizaines de milliers de lignes
    # pour un complexe).
    dates = records.order_by("-date").values_list("date", flat=True).distinct()
    page_obj = paginate(request, dates, per_page=5, param="historique_page")
    page_dates = list(page_obj.object_list)
    history_groups = []
    current_date = None
    current_group = None
    if selected_class_id:
        page_records = records.filter(date__in=page_dates).order_by(
            "-date", "enrollment__classe__name", "enrollment__student__last_name", "enrollment__student__first_name"
        ) if page_dates else records.none()
        for record in page_records:
            if record.date != current_date:
                current_date = record.date
                current_group = {"date": record.date, "records": [], "summary": None}
                history_groups.append(current_group)
            current_group["records"].append(record)
    elif page_dates:
        # Sans classe choisie : synthèse par classe et par date (quelques
        # dizaines de lignes) au lieu du détail de chaque élève de l'école.
        class_by_id = {c.id: c for c in classes}
        summary_rows = (
            records.filter(date__in=page_dates).order_by()
            .values("date", "enrollment__classe_id")
            .annotate(
                total=Count("id"),
                present=Count("id", filter=Q(status="PRESENT")),
                absent=Count("id", filter=Q(status="ABSENT")),
                late=Count("id", filter=Q(status="LATE")),
            )
            .order_by("-date")
        )
        for row in summary_rows:
            if row["date"] != current_date:
                current_date = row["date"]
                current_group = {"date": row["date"], "records": [], "summary": []}
                history_groups.append(current_group)
            row["classe"] = class_by_id.get(row["enrollment__classe_id"])
            current_group["summary"].append(row)
        for group in history_groups:
            group["summary"].sort(key=lambda r: (r["classe"].education_level.order, r["classe"].name) if r["classe"] else (0, ""))
            group["total"] = sum(r["total"] for r in group["summary"])

    return render(request, "vie_scolaire/attendance_list.html", {
        "history_groups": history_groups,
        "history_page": page_obj,
        "current_day_recorded": bool(attendance_map),
        "classes": classes,
        "selected_class": selected_class,
        "selected_class_id": str(selected_class_id),
        "selected_date": selected_date,
        "enrollments": enrollments,
        "attendance_map": attendance_map,
        "draft_attendance_map": draft_attendance_map,
        "school_year": year,
        "history_date": history_date or "",
    })


@login_required
def attendance_mark(request, classe_id):
    """Compatibilité avec l'ancien lien : renvoie vers l'écran unique."""
    year = viewed_year()
    classe = get_object_or_404(Classe, pk=classe_id, school_year=year)
    selected_date = request.POST.get("date") or request.GET.get("date") or timezone.localdate()
    if hasattr(selected_date, "isoformat"):
        selected_date = selected_date.isoformat()
    url = f"{reverse('attendance_list')}?classe={classe.id}&date={selected_date}"
    return redirect(url)


@login_required
@transaction.atomic
def staff_attendance_list(request):
    """Écran de pointage du personnel (enseignants + autre personnel).

    Contrairement aux présences élèves, une présence du personnel reste
    modifiable après enregistrement : c'est la base de calcul des états de
    salaires (annuel et horaire), donc une correction doit rester possible
    sans passer par un mécanisme administratif séparé.
    """
    year = viewed_year()
    selected_date_raw = request.POST.get("date") or request.GET.get("date") or ""
    selected_date = timezone.localdate()
    if selected_date_raw:
        try:
            from datetime import date as date_cls
            selected_date = date_cls.fromisoformat(selected_date_raw)
        except (TypeError, ValueError):
            messages.error(request, "La date sélectionnée est invalide.")

    teachers = []
    others = []
    if year:
        teachers = list(Teacher.objects.filter(is_active=True).select_related("user").order_by("last_name", "first_name"))
        others = list(OtherPersonnel.objects.filter(is_active=True, school=year.school).order_by("last_name", "first_name"))

    rows = [{"kind": "teacher", "id": t.id, "prefix": f"teacher_{t.id}", "label": t.full_name, "sub": t.get_contract_type_display()} for t in teachers]
    rows += [{"kind": "other", "id": p.id, "prefix": f"other_{p.id}", "label": f"{p.first_name} {p.last_name}", "sub": p.function} for p in others]

    existing_teacher = {r.teacher_id: r for r in TeacherAttendance.objects.filter(school_year=year, date=selected_date)} if year else {}
    existing_other = {r.personnel_id: r for r in OtherPersonnelAttendance.objects.filter(school_year=year, date=selected_date)} if year else {}

    if request.method == "POST" and year:
        allowed_statuses = {"PRESENT", "ABSENT", "LATE"}
        errors = []
        for row in rows:
            prefix = row["prefix"]
            status = request.POST.get(f"status_{prefix}", "PRESENT")
            if status not in allowed_statuses:
                status = "PRESENT"
            entry_time = request.POST.get(f"entry_time_{prefix}", "").strip() or None
            exit_time = request.POST.get(f"exit_time_{prefix}", "").strip() or None
            raw_minutes = request.POST.get(f"late_minutes_{prefix}", "").strip()
            late_minutes = int(raw_minutes) if raw_minutes.isdigit() and int(raw_minutes) > 0 else None
            note = request.POST.get(f"note_{prefix}", "").strip()
            try:
                if row["kind"] == "teacher":
                    obj, _ = TeacherAttendance.objects.update_or_create(
                        teacher_id=row["id"], school_year=year, date=selected_date,
                        defaults={"status": status, "entry_time": entry_time, "exit_time": exit_time, "late_minutes": late_minutes, "note": note, "recorded_by": request.user},
                    )
                else:
                    obj, _ = OtherPersonnelAttendance.objects.update_or_create(
                        personnel_id=row["id"], school_year=year, date=selected_date,
                        defaults={"status": status, "entry_time": entry_time, "exit_time": exit_time, "late_minutes": late_minutes, "note": note, "recorded_by": request.user},
                    )
            except ValidationError as exc:
                errors.append(f"{row['label']} : {'; '.join(exc.messages) if hasattr(exc, 'messages') else exc}")
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            messages.success(request, "Pointage du personnel enregistré pour cette date.")
        existing_teacher = {r.teacher_id: r for r in TeacherAttendance.objects.filter(school_year=year, date=selected_date)}
        existing_other = {r.personnel_id: r for r in OtherPersonnelAttendance.objects.filter(school_year=year, date=selected_date)}

    for row in rows:
        record = existing_teacher.get(row["id"]) if row["kind"] == "teacher" else existing_other.get(row["id"])
        row["record"] = record

    return render(request, "vie_scolaire/staff_attendance_list.html", {
        "rows": rows,
        "selected_date": selected_date,
        "school_year": year,
    })


@login_required
def discipline_list(request):
    year = viewed_year()
    incidents = (DisciplineIncident.objects.filter(enrollment__school_year=year).select_related("enrollment__student", "enrollment__classe__education_level", "enrollment__classe__pedagogical_track") if year else DisciplineIncident.objects.none())
    form = DisciplineEntryForm(request.POST or None, school_year=year)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.enrollment = form.cleaned_data["enrollment"]
        obj.recorded_by = request.user
        obj.save()
        messages.success(request, "Événement disciplinaire enregistré.")
        return redirect("discipline_list")
    page_obj = paginate(request, incidents)
    if year:
        from common import whatsapp
        for incident in page_obj:
            incident.whatsapp_url = whatsapp.wa_url(whatsapp.family_phone(incident.enrollment.student),
                                                    whatsapp.discipline_text(incident, year.school))
    return render(request, "vie_scolaire/discipline_list.html", {"incidents": page_obj, "page_obj": page_obj, "form": form})


@login_required
def discipline_create(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment, pk=enrollment_id)
    form = DisciplineIncidentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.enrollment = enrollment
        obj.recorded_by = request.user
        obj.save()
        messages.success(request, "Événement de vie scolaire enregistré.")
        return redirect("discipline_list")
    return render(request, "vie_scolaire/discipline_form.html", {"form": form, "enrollment": enrollment})


@login_required
def discipline_students(request, classe_id):
    year = viewed_year()
    enrollments = Enrollment.objects.filter(school_year=year, classe_id=classe_id).select_related("student").order_by("student__last_name", "student__first_name") if year else Enrollment.objects.none()
    options = ["<option value=\"\">Sélectionnez un élève</option>"]
    options += [f'<option value="{e.id}">{e.student.first_name} {e.student.last_name}</option>' for e in enrollments]
    return HttpResponse("".join(options))


@login_required
def attendance_week_pdf(request):
    from io import BytesIO
    from datetime import timedelta
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    year = viewed_year()
    if not year:
        return HttpResponse("Aucune année scolaire active.", status=400)
    classes = Classe.objects.filter(school_year=year).order_by("education_level__order", "name")
    classe_id = request.GET.get("classe", "")
    try:
        anchor = timezone.localdate()
        if request.GET.get("date"):
            from datetime import date
            anchor = date.fromisoformat(request.GET["date"])
    except ValueError:
        anchor = timezone.localdate()
    monday = anchor - timedelta(days=anchor.weekday())
    sunday = monday + timedelta(days=6)
    qs = Attendance.objects.filter(enrollment__school_year=year, date__range=(monday, sunday)).select_related("enrollment__student", "enrollment__classe")
    if classe_id:
        qs = qs.filter(enrollment__classe_id=classe_id)
    records = list(qs.order_by("enrollment__classe__name", "enrollment__student__last_name", "enrollment__student__first_name", "date"))
    students = {}
    for r in records: students.setdefault(r.enrollment_id, {"student":r.enrollment.student,"classe":r.enrollment.classe,"days":{}})["days"][r.date]=r
    buffer=BytesIO(); doc=SimpleDocTemplate(buffer,pagesize=landscape(A4),rightMargin=8*mm,leftMargin=8*mm,topMargin=10*mm,bottomMargin=12*mm,title="Liste des présences de la semaine")
    styles=getSampleStyleSheet(); small=ParagraphStyle("AttSmall",parent=styles["Normal"],fontSize=7,leading=8); title=ParagraphStyle("AttTitle",parent=styles["Title"],fontSize=14,alignment=1,spaceAfter=5*mm)
    story=[Paragraph(f"<b>{escape(year.school.name)}</b>", small), Paragraph(f"LISTE DES PRÉSENCES — SEMAINE DU {monday:%d/%m/%Y} AU {sunday:%d/%m/%Y}",title)]
    if classe_id:
        c=classes.filter(pk=classe_id).first()
        if c: story.append(Paragraph(f"Classe : {escape(c.display_name)}", small))
    data=[["N°","ÉLÈVE","CLASSE"]+[d.strftime("%a %d") for d in [monday+timedelta(days=i) for i in range(7)]]+["Abs.","Ret."]]
    for i,row in enumerate(students.values(),1):
        vals=[]; absn=ret=0
        for d in [monday+timedelta(days=i) for i in range(7)]:
            r=row["days"].get(d); v="" if not r else ("P" if r.status=="PRESENT" else "A" if r.status=="ABSENT" else "R")
            if r and r.status=="ABSENT": absn+=1
            if r and r.status=="LATE": ret+=1
            vals.append(v)
        data.append([f"{i:02d}",f"{row['student'].first_name} {row['student'].last_name}",row["classe"].display_name]+vals+[str(absn),str(ret)])
    table=Table(data,colWidths=[8*mm,48*mm,30*mm]+[18*mm]*7+[12*mm,12*mm],repeatRows=1); table.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.3,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.lightgrey),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),7),("ALIGN",(0,0),(-1,-1),"CENTER"),("ALIGN",(1,1),(2,-1),"LEFT")]))
    story += [Spacer(1,3*mm),table,Spacer(1,4*mm),Paragraph("Légende : P = Présent · A = Absent · R = Retard",small)]
    def footer(canvas,doc):
        canvas.saveState(); canvas.setFont("Helvetica-Oblique",8); motto=getattr(year.school,"motto","")
        if motto: canvas.drawCentredString(landscape(A4)[0]/2,7*mm,motto)
        canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer); response=HttpResponse(buffer.getvalue(),content_type="application/pdf"); response["Content-Disposition"]='inline; filename="presences-semaine.pdf"'; return response
