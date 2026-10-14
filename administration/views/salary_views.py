"""Salaires (retours du 08/10) : annulation de paiements saisis par erreur et bulletin de salaire.

- Annulation : on coche les paiements faits par erreur (par exemple tous les
  mois de l'année saisis d'un coup), on indique le motif, et ils sont retirés.
  Chaque annulation est inscrite au journal des corrections (personne,
  période, montant), rien ne disparaît sans trace.
- Bulletin de salaire : un paiement = une page A4 avec deux exemplaires
  identiques, l'un pour le salarié, l'autre pour les archives de l'établissement.
"""
from io import BytesIO
from xml.sax.saxutils import escape

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from administration.models import CorrectionLog, OtherPersonnelPayment, School, TeacherPayment
from administration.permissions import permission_required
from common.montant_lettres import en_lettres
from common.years import viewed_year

KINDS = {
    "enseignants": {"model": TeacherPayment, "person": "teacher", "label": "enseignants", "list": "teacher_payment_list"},
    "personnel": {"model": OtherPersonnelPayment, "person": "personnel", "label": "personnel non enseignant", "list": "other_personnel_payment_list"},
}


def _kind(kind):
    if kind not in KINDS:
        raise Http404
    return KINDS[kind]


def _person(payment):
    return getattr(payment, "teacher", None) or getattr(payment, "personnel")


def _person_name(person):
    return getattr(person, "full_name", None) or f"{person.first_name} {person.last_name}".strip()


def _person_function(person):
    if hasattr(person, "function"):
        return person.function
    profile = person.get_pedagogical_profile_display() if getattr(person, "pedagogical_profile", "") else ""
    return " · ".join(x for x in ("Enseignant", profile, getattr(person, "specialty", "")) if x)


@login_required
@permission_required("data.correct")
def salary_cancel(request, kind):
    conf = _kind(kind)
    year = viewed_year()
    model, person = conf["model"], conf["person"]
    payments = model.objects.filter(school_year=year).select_related(person).order_by(f"{person}__last_name", "paid_at", "id") if year else model.objects.none()
    q = (request.GET.get("q") or request.POST.get("q") or "").strip()
    if q:
        payments = payments.filter(Q(**{f"{person}__last_name__icontains": q}) | Q(**{f"{person}__first_name__icontains": q})
                                   | Q(**{f"{person}__employee_number__icontains": q}) | Q(period__icontains=q))
    error = None
    if request.method == "POST":
        ids = [i for i in request.POST.getlist("payment") if i.isdigit()]
        reason = (request.POST.get("reason") or "").strip()
        chosen = list(model.objects.filter(pk__in=ids, school_year=year).select_related(person))
        if not chosen:
            error = "Cochez au moins un paiement à annuler."
        elif len(reason) < 3:
            error = "Indiquez le motif de l'annulation."
        elif year and year.is_closed:
            error = "Cette année est clôturée : ses salaires ne peuvent plus être annulés."
        else:
            total = sum(p.amount for p in chosen)
            detail = "; ".join(f"{_person_name(_person(p))} — {p.period} — {p.amount:,.0f} (payé le {p.paid_at:%d/%m/%Y})".replace(",", " ")
                               for p in chosen)
            with transaction.atomic():
                CorrectionLog.objects.create(
                    action=CorrectionLog.Action.SALARY_CANCEL,
                    description=f"{len(chosen)} paiement(s) de salaire ({conf['label']}, {year.name}) annulé(s) : {detail}"[:5000],
                    reason=reason, amount=total, user=request.user if request.user.pk else None,
                    student_label=f"Salaires {conf['label']}",
                )
                model.objects.filter(pk__in=[p.pk for p in chosen]).delete()
            messages.success(request, f"{len(chosen)} paiement(s) annulé(s) pour {total:,.0f} FCFA. Le détail est conservé dans le journal des corrections.".replace(",", " "))
            return redirect(conf["list"])
    return render(request, "administration/salaries/cancel.html", {
        "payments": payments, "kind": kind, "conf": conf, "school_year": year, "q": q, "error": error,
        "reason": request.POST.get("reason", ""), "chosen": set(request.POST.getlist("payment")),
    })


def _draw_copy(c, top, width, school, payment, copy_label):
    """Dessine un exemplaire du bulletin dans la moitié de page commençant à ``top`` (en points)."""
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Paragraph, Table, TableStyle

    person = _person(payment)
    left = 15 * mm
    y = top - 12 * mm
    logo_w = 0
    try:
        if school.logo:
            school.logo.open("rb")
            try:
                c.drawImage(ImageReader(school.logo), left, y - 14 * mm, width=16 * mm, height=16 * mm,
                            preserveAspectRatio=True, mask="auto")
                logo_w = 19 * mm
            finally:
                school.logo.close()
    except Exception:
        logo_w = 0
    c.setFillColor(colors.HexColor("#0F2D5C"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(left + logo_w, y - 1 * mm, school.name)
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#475569"))
    contact = " · ".join(x for x in (school.address, school.city, f"Tél. {school.phone}" if school.phone else "") if x)
    c.drawString(left + logo_w, y - 6 * mm, contact[:110])
    c.setFillColor(colors.HexColor("#0F2D5C"))
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(width - left, y - 1 * mm, "BULLETIN DE SALAIRE")
    c.setFont("Helvetica-Oblique", 8.5)
    c.setFillColor(colors.HexColor("#B45309"))
    c.drawRightString(width - left, y - 6 * mm, copy_label)

    label = ParagraphStyle("l", fontName="Helvetica-Bold", fontSize=9, leading=11)
    value = ParagraphStyle("v", fontName="Helvetica", fontSize=9, leading=11)
    rows = [
        ["Nom et prénom(s)", _person_name(person), "Matricule", person.employee_number or "—"],
        ["Fonction", _person_function(person) or "—", "Statut", person.get_contract_type_display()],
        ["Période", payment.period, "Année scolaire", payment.school_year.name],
        ["Date de paiement", payment.paid_at.strftime("%d/%m/%Y"), "Observation", payment.note or "—"],
    ]
    data = [[Paragraph(escape(str(a)), label), Paragraph(escape(str(b)), value), Paragraph(escape(str(cc)), label),
             Paragraph(escape(str(d)), value)] for a, b, cc, d in rows]
    t = Table(data, colWidths=[34 * mm, 58 * mm, 30 * mm, (width - 2 * left) - 122 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C8D0DA")),
                           ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F6FA")),
                           ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F3F6FA")),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    w, h = t.wrapOn(c, width - 2 * left, 80 * mm)
    t.drawOn(c, left, y - 14 * mm - h)
    y = y - 14 * mm - h - 6 * mm

    amount = f"{payment.amount:,.0f} FCFA".replace(",", " ")
    box = Table([[Paragraph("<b>NET PAYÉ</b>", ParagraphStyle("n", fontName="Helvetica-Bold", fontSize=11, textColor=colors.white)),
                  Paragraph(f"<b>{amount}</b>", ParagraphStyle("a", fontName="Helvetica-Bold", fontSize=13, alignment=2, textColor=colors.white))]],
                colWidths=[60 * mm, (width - 2 * left) - 60 * mm])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0F2D5C")),
                             ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    w, h = box.wrapOn(c, width - 2 * left, 20 * mm)
    box.drawOn(c, left, y - h)
    y -= h + 5 * mm
    words = Paragraph(f"Arrêté le présent bulletin à la somme de : <b>{escape(en_lettres(payment.amount))} francs CFA</b>.",
                      ParagraphStyle("w", fontName="Helvetica", fontSize=9, leading=11))
    w, h = words.wrapOn(c, width - 2 * left, 20 * mm)
    words.drawOn(c, left, y - h)
    y -= h + 10 * mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(left, y, "Signature du salarié")
    c.drawRightString(width - left, y, "Pour l'établissement (cachet et signature)")
    c.setFont("Helvetica", 6.5)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawString(left, top - 140 * mm + 4 * mm, "Document généré par KIS Kalanso")


@login_required
@permission_required("salaries.manage")
def salary_payslip_pdf(request, kind, pk):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    conf = _kind(kind)
    payment = get_object_or_404(conf["model"].objects.select_related(conf["person"], "school_year__school"), pk=pk)
    school = payment.school_year.school or School.objects.filter(is_active=True).first()
    buffer = BytesIO()
    width, height = A4
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f"Bulletin de salaire — {_person_name(_person(payment))} — {payment.period}")
    _draw_copy(c, height, width, school, payment, "Exemplaire du salarié")
    c.setDash(3, 3)
    c.setStrokeColor(colors.HexColor("#94A3B8"))
    c.line(8 * mm, height / 2, width - 8 * mm, height / 2)
    c.setDash()
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#94A3B8"))
    c.drawCentredString(width / 2, height / 2 + 1.5 * mm, "- - - découper ici - - -")
    _draw_copy(c, height / 2, width, school, payment, "Exemplaire des archives de l'établissement")
    c.showPage()
    c.save()
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    name = _person_name(_person(payment)).replace(" ", "_")
    response["Content-Disposition"] = f'inline; filename="bulletin_salaire_{name}_{payment.period.replace(" ", "_")}.pdf"'
    return response
