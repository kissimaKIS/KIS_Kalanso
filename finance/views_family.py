"""Finances regroupées par famille (V5-3) : liste des familles, impayés par famille."""
from decimal import Decimal
from xml.sax.saxutils import escape

from django.contrib.auth.decorators import login_required
from django.db.models import DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import render

from pedagogie.models import Enrollment
from .services.grouped_payment import _name, _phone, family_label, family_phone, group_families
from .views import _draw_internal_footer, _finance_year_context, _school_identity_story, _selected_year
from .views_grouped import _grid, _money, _pdf_styles

ZERO = Value(Decimal("0"), output_field=DecimalField(max_digits=12, decimal_places=0))


def _families(request, year):
    if not year:
        return [], {}
    enrollments = (Enrollment.objects.filter(school_year=year)
                   .select_related("student", "classe__education_level", "classe__pedagogical_track")
                   .annotate(total=Coalesce(Sum("invoices__total_amount"), ZERO),
                             paid=Coalesce(Sum("invoices__paid_amount"), ZERO)))
    # Reliquats encore dus sur les autres années (années antérieures ou reprises).
    from .models import Invoice
    arrears = {}
    for student_id, due in (Invoice.objects.exclude(enrollment__school_year=year)
                            .filter(paid_amount__lt=F("total_amount"))
                            .values_list("enrollment__student_id").annotate(d=Sum(F("total_amount") - F("paid_amount")))):
        arrears[student_id] = due
    families = []
    for members in group_families(enrollments):
        total = sum((m.total for m in members), Decimal("0"))
        paid = sum((m.paid for m in members), Decimal("0"))
        old = sum((arrears.get(m.student_id, Decimal("0")) for m in members), Decimal("0"))
        families.append({
            "members": members, "label": family_label(members), "phone": family_phone(members),
            "total": total, "paid": paid, "arrears": old, "rest": total - paid + old, "first": members[0],
        })
    filters = {
        "q": (request.GET.get("q") or "").strip(),
        "tous": request.GET.get("tous") == "1",
        "du": request.GET.get("du") == "1",
    }
    if not filters["tous"]:
        families = [f for f in families if len(f["members"]) >= 2]
    if filters["du"]:
        families = [f for f in families if f["rest"] > 0]
    if filters["q"]:
        q_name, q_phone = _name(filters["q"]), _phone(filters["q"])
        def match(f):
            if q_phone and any(q_phone in {_phone(m.student.father_phone), _phone(m.student.mother_phone), _phone(m.student.whatsapp_phone)} for m in f["members"]):
                return True
            text = _name(f["label"] + " " + " ".join(f"{m.student.last_name} {m.student.first_name}" for m in f["members"]))
            return q_name in text
        families = [f for f in families if match(f)]
    families.sort(key=lambda f: (-f["rest"], f["label"].lower()))
    return families, filters


@login_required
def family_list(request):
    year = _selected_year(request)
    families, filters = _families(request, year)
    context = _finance_year_context(request, year)
    context.update({
        "families": families, "filters": filters,
        "totals": {
            "count": len(families), "children": sum(len(f["members"]) for f in families),
            "total": sum((f["total"] for f in families), Decimal("0")),
            "paid": sum((f["paid"] for f in families), Decimal("0")),
            "arrears": sum((f["arrears"] for f in families), Decimal("0")),
            "rest": sum((f["rest"] for f in families), Decimal("0")),
        },
    })
    return render(request, "finance/families/list.html", context)


@login_required
def family_list_pdf(request):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    year = _selected_year(request)
    if not year:
        return HttpResponse("Aucune année scolaire.", status=400)
    families, filters = _families(request, year)
    school = year.school
    cur = school.currency
    st = _pdf_styles()
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="familles.pdf"'
    page = landscape(A4)
    doc = SimpleDocTemplate(response, pagesize=page, rightMargin=12 * mm, leftMargin=12 * mm, topMargin=12 * mm,
                            bottomMargin=16 * mm, title="Situation par famille", author=school.name)
    width = page[0] - 24 * mm
    title = "IMPAYÉS PAR FAMILLE" if filters["du"] else "SITUATION FINANCIÈRE PAR FAMILLE"
    story = [_school_identity_story(school, st["styles"], width), Spacer(1, 4 * mm),
             Paragraph(title, st["title"]), Paragraph(f"Année scolaire {escape(year.name)}", st["center"]), Spacer(1, 4 * mm)]
    data = [[Paragraph(h, st["head"]) for h in ("N°", "Parents", "Téléphone", "Enfants (classe)", "Montant", "Payé", "Reliquats ant.", "Reste")]]
    for i, f in enumerate(families, 1):
        kids = "<br/>".join(f"{escape(m.student.last_name)} {escape(m.student.first_name)} ({escape(m.classe.display_name)})" for m in f["members"])
        data.append([Paragraph(str(i), st["cell"]), Paragraph(escape(f["label"]), st["cell"]), Paragraph(escape(f["phone"] or "—"), st["cell"]),
                     Paragraph(kids, st["cell"]), Paragraph(_money(f["total"], cur), st["cellr"]),
                     Paragraph(_money(f["paid"], cur), st["cellr"]), Paragraph(_money(f["arrears"], cur) if f["arrears"] else "—", st["cellr"]),
                     Paragraph(_money(f["rest"], cur), st["cellb"])])
    total = sum((f["total"] for f in families), Decimal("0"))
    paid = sum((f["paid"] for f in families), Decimal("0"))
    old = sum((f["arrears"] for f in families), Decimal("0"))
    rest = sum((f["rest"] for f in families), Decimal("0"))
    data.append([Paragraph("", st["cell"]), Paragraph(f"<b>{len(families)} famille(s)</b>", st["cell"]), Paragraph("", st["cell"]),
                 Paragraph(f"<b>{sum(len(f['members']) for f in families)} enfant(s)</b>", st["cell"]),
                 Paragraph(_money(total, cur), st["cellb"]), Paragraph(_money(paid, cur), st["cellb"]),
                 Paragraph(_money(old, cur), st["cellb"]), Paragraph(_money(rest, cur), st["cellb"])])
    fixed = 10 * mm + 28 * mm + 4 * 28 * mm
    story.append(_grid(data, [10 * mm, (width - fixed) * 0.4, 28 * mm, (width - fixed) * 0.6, 28 * mm, 28 * mm, 28 * mm, 28 * mm], total_row=True))
    footer = lambda c, d: _draw_internal_footer(c, d, school)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return response
