from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import escape
from django.http import HttpResponse
from .models import Announcement
from .forms import AnnouncementForm
def _is_modal_request(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _modal_reload_response():
    return HttpResponse("", headers={"HX-Trigger": "kisModalReload"})

@login_required
def announcement_list(request):
    return render(request, "communication/list.html", {"announcements": Announcement.objects.select_related("author")})
@login_required
def announcement_create(request):
    form = AnnouncementForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj=form.save(commit=False); obj.author=request.user; obj.save(); messages.success(request,"Annonce publiée.")
        if _is_modal_request(request): return _modal_reload_response()
        return redirect("announcement_list")
    if _is_modal_request(request): return render(request,"communication/_modal_form.html",{"form":form,"action_url":request.path})
    return render(request,"communication/form.html",{"form":form})
@login_required
def announcement_update(request, pk):
    """Corriger une annonce déjà publiée (faute de frappe, date, destinataires…)."""
    from django.utils import timezone
    obj = get_object_or_404(Announcement, pk=pk)
    form = AnnouncementForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.updated_at = timezone.now()
        obj.save()
        messages.success(request, "Annonce modifiée.")
        if _is_modal_request(request): return _modal_reload_response()
        return redirect("announcement_list")
    if _is_modal_request(request): return render(request, "communication/_modal_form.html", {"form": form, "action_url": request.path})
    return render(request, "communication/form.html", {"form": form, "editing": True})


@login_required
def announcement_delete(request, pk):
    obj=get_object_or_404(Announcement,pk=pk)
    if request.method=="POST": obj.delete(); messages.success(request,"Annonce supprimée."); return redirect("announcement_list")
    return render(request,"communication/confirm_delete.html",{"object":obj})


@login_required
def announcement_pdf(request, pk):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    announcement = get_object_or_404(Announcement.objects.select_related("author"), pk=pk)
    school = getattr(request, "school", None)
    if school is None:
        from administration.models import School
        school = School.objects.filter(is_active=True).first()
    buffer = __import__("io").BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm, topMargin=18*mm, bottomMargin=18*mm, title=announcement.title)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="School", parent=styles["Normal"], alignment=TA_CENTER, fontSize=10))
    styles.add(ParagraphStyle(name="TitleKIS", parent=styles["Title"], alignment=TA_CENTER, spaceAfter=10))
    styles.add(ParagraphStyle(name="BodyKIS", parent=styles["BodyText"], fontSize=11, leading=16, spaceAfter=8))
    story=[]
    if school:
        story.append(Paragraph(f"<b>{escape(school.name)}" + (f" ({escape(school.code)})" if school.code else "") + "</b>", styles["School"]))
        contact = " — ".join([x for x in [school.address, school.city, f"Tél. : {school.phone}" if school.phone else "", school.email] if x])
        if contact: story.append(Paragraph(escape(contact), styles["School"]))
        story.append(Spacer(1, 10*mm))
    story += [Paragraph(escape(announcement.title), styles["TitleKIS"]), Paragraph(announcement.published_at.strftime("%d/%m/%Y %H:%M"), styles["School"]), Spacer(1, 8*mm), Paragraph(escape(announcement.message).replace("\n", "<br/>"), styles["BodyKIS"]), Paragraph(f"Destinataires : {escape(announcement.get_audience_display())}", styles["BodyKIS"])]
    def footer(canvas, doc):
        motto = getattr(school, "motto", "") if school else ""
        if motto:
            canvas.saveState(); canvas.setFont("Helvetica-Oblique", 8); canvas.setFillColor(colors.grey); canvas.drawCentredString(A4[0]/2, 7*mm, motto); canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    response=HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="annonce-{announcement.pk}.pdf"'
    return response


@login_required
def announcement_whatsapp(request, pk):
    """Envoi assisté d'une annonce par WhatsApp : une ligne par famille (ou par membre du personnel)."""
    from administration.models import OtherPersonnel, School, Teacher
    from common import whatsapp
    from common.years import active_year
    from finance.services.grouped_payment import family_label, group_families
    from pedagogie.models import Classe, Enrollment

    announcement = get_object_or_404(Announcement, pk=pk)
    school = School.objects.filter(is_active=True).first()
    text = whatsapp.announcement_text(announcement, school)
    year = active_year()
    staff_audience = announcement.audience in ("TEACHERS", "SECRETARY")
    classe = None
    rows = []
    if staff_audience:
        people = list(Teacher.objects.filter(is_active=True).order_by("last_name", "first_name"))
        if announcement.audience == "SECRETARY":
            people = list(OtherPersonnel.objects.order_by("last_name", "first_name"))
        for person in people:
            rows.append({"label": f"{person.last_name} {person.first_name}", "detail": "", "phone": person.phone,
                         "url": whatsapp.wa_url(person.phone, text)})
    elif year:
        enrollments = Enrollment.objects.filter(school_year=year).select_related("student", "classe")
        classe = Classe.objects.filter(school_year=year, pk=request.GET.get("classe") or 0).first()
        if classe:
            enrollments = enrollments.filter(classe=classe)
        for members in group_families(enrollments):
            phone = next((whatsapp.family_phone(m.student) for m in members if whatsapp.family_phone(m.student)), "")
            rows.append({"label": family_label(members),
                         "detail": ", ".join(f"{m.student.first_name} ({m.classe.display_name})" for m in members),
                         "phone": phone, "url": whatsapp.wa_url(phone, text)})
        rows.sort(key=lambda r: r["label"].lower())
    classes = (Classe.objects.filter(school_year=year).select_related("education_level").order_by("education_level__order", "group", "name")
               if year and not staff_audience else [])
    return render(request, "communication/whatsapp.html", {
        "announcement": announcement, "rows": rows, "text": text, "classes": classes, "classe": classe,
        "staff_audience": staff_audience, "without_phone": sum(1 for r in rows if not r["url"]),
    })
