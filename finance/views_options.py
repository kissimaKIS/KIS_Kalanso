"""Listes d'élèves par option (cantine, transport, uniforme…) avec impression (V5-7)."""
from decimal import Decimal
from xml.sax.saxutils import escape

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import render

from administration.permissions import user_has_permission
from pedagogie.models import Classe
from .models import FeeType, Invoice, StudentOption
from .views import _draw_internal_footer, _finance_year_context, _school_identity_story, _selected_year
from .views_grouped import _grid, _money, _pdf_styles


class _Poste:
    """Un poste d'un frais détaillé (ex. « Manuel » de l'inscription préscolaire), listé comme une option."""
    allows_quantity = False

    def __init__(self, component):
        self.component = component
        self.id = f"p{component.pk}"
        fee = component.fee_type
        scope = fee.get_school_type_display() if fee.school_type else (fee.education_level.name if fee.education_level_id else "")
        self.fee_name = f"{fee.name} ({scope})" if scope else fee.name
        self.name = f"{component.name} — {self.fee_name}"
        self.nb = getattr(component, "nb", 0)


def _postes(year):
    from .models import FeeComponent
    comps = (FeeComponent.objects.filter(fee_type__school_year=year)
             .select_related("fee_type__education_level")
             .annotate(nb=Count("invoice_lines", filter=Q(invoice_lines__amount__gt=0), distinct=True))
             .order_by("fee_type__name", "fee_type__school_type", "order", "id"))
    return [_Poste(c) for c in comps]


def _keep(status, amount, paid):
    reste = max(Decimal("0"), amount - paid)
    if status == "solde":
        return reste == 0
    if status == "du":
        return reste > 0
    if status == "partiel":
        return paid > 0 and reste > 0
    if status == "rien":
        return paid == 0
    return True


def _option_rows(request, year):
    options = FeeType.objects.none()
    postes = []
    fee = classe = None
    status = request.GET.get("statut", "")
    rows = []
    chosen = request.GET.get("option") or ""
    if year:
        options = (FeeType.objects.filter(school_year=year, category=FeeType.Category.OPTIONAL)
                   .annotate(nb=Count("invoices", distinct=True)).order_by("name"))
        postes = _postes(year)
        if chosen.startswith("p"):
            fee = next((p for p in postes if p.id == chosen), None)
        elif chosen.isdigit():
            fee = options.filter(pk=chosen).first()
        classe = Classe.objects.filter(school_year=year, pk=request.GET.get("classe") or 0).first()
    if isinstance(fee, _Poste):
        from .models import InvoiceLine
        lines = InvoiceLine.objects.filter(component=fee.component, amount__gt=0, invoice__enrollment__school_year=year).select_related(
            "invoice__enrollment__student", "invoice__enrollment__classe__education_level", "invoice__enrollment__classe__pedagogical_track")
        if classe:
            lines = lines.filter(invoice__enrollment__classe=classe)
        for line in lines:
            if not _keep(status, line.amount, line.paid_amount):
                continue
            e = line.invoice.enrollment
            rows.append({"invoice": line.invoice, "student": e.student, "classe": e.classe, "quantity": None, "price": None,
                         "amount": line.amount, "paid": line.paid_amount, "reste": line.reste})
    elif fee:
        invoices = Invoice.objects.filter(fee_type=fee, enrollment__school_year=year).select_related(
            "enrollment__student", "enrollment__classe__education_level", "enrollment__classe__pedagogical_track")
        if classe:
            invoices = invoices.filter(enrollment__classe=classe)
        quantities = {o.enrollment_id: o for o in StudentOption.objects.filter(fee_type=fee, enrollment__school_year=year)}
        for inv in invoices:
            if not _keep(status, inv.total_amount, inv.paid_amount):
                continue
            option = quantities.get(inv.enrollment_id)
            rows.append({
                "invoice": inv, "student": inv.enrollment.student, "classe": inv.enrollment.classe,
                "quantity": option.quantity if option and fee.allows_quantity else None,
                "price": option.price if option and fee.allows_quantity else None,
                "amount": inv.total_amount, "paid": inv.paid_amount, "reste": inv.reste,
            })
    rows.sort(key=lambda r: (r["classe"].education_level.order, r["classe"].display_name,
                             r["student"].last_name.lower(), r["student"].first_name.lower()))
    return options, postes, fee, classe, status, rows


def _totals(rows):
    return {
        "count": len(rows),
        "quantity": sum(r["quantity"] or 0 for r in rows),
        "total": sum((r["amount"] for r in rows), Decimal("0")),
        "paid": sum((r["paid"] for r in rows), Decimal("0")),
        "rest": sum((r["reste"] for r in rows), Decimal("0")),
    }


@login_required
def option_lists(request):
    year = _selected_year(request)
    options, postes, fee, classe, status, rows = _option_rows(request, year)
    context = _finance_year_context(request, year)
    to_ventilate = 0
    if isinstance(fee, _Poste):
        from .services.components import invoices_to_ventilate
        to_ventilate = len(invoices_to_ventilate(fee=fee.component.fee_type, school_year=year))
    context.update({
        "options": options, "postes": postes, "is_poste": isinstance(fee, _Poste), "to_ventilate": to_ventilate, "fee": fee, "classe": classe, "status": status, "rows": rows,
        "totals": _totals(rows),
        "classes": Classe.objects.filter(school_year=year).select_related("education_level", "pedagogical_track")
                   .order_by("education_level__order", "group", "name") if year else [],
        "show_money": user_has_permission(request.user, "finance.collect"),
    })
    return render(request, "finance/options/lists.html", context)


@login_required
def option_list_pdf(request):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    year = _selected_year(request)
    options, postes, fee, classe, status, rows = _option_rows(request, year)
    if not fee:
        return HttpResponse("Choisissez une option.", status=400)
    show_money = user_has_permission(request.user, "finance.collect") and request.GET.get("montants") != "0"
    school = year.school
    cur = school.currency
    st = _pdf_styles()
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="liste_{str(fee.id)}.pdf"'
    doc = SimpleDocTemplate(response, pagesize=A4, rightMargin=14 * mm, leftMargin=14 * mm, topMargin=14 * mm,
                            bottomMargin=16 * mm, title=f"Liste — {fee.name}", author=school.name)
    width = A4[0] - 28 * mm
    subtitle = f"Année scolaire {escape(year.name)}"
    if classe:
        subtitle += f" · Classe : {escape(classe.display_name)}"
    if status == "solde":
        subtitle += " · Soldés uniquement"
    elif status == "du":
        subtitle += " · Restant dû uniquement"
    elif status == "partiel":
        subtitle += " · Payé en partie"
    elif status == "rien":
        subtitle += " · Rien payé"
    story = [_school_identity_story(school, st["styles"], width), Spacer(1, 5 * mm),
             Paragraph(f"LISTE DES ÉLÈVES — {escape(fee.name.upper())}", st["title"]),
             Paragraph(subtitle, st["center"]), Spacer(1, 5 * mm)]
    head = ["N°", "Élève", "Classe"]
    widths = [10 * mm, None, 32 * mm]
    if fee.allows_quantity:
        head.append("Qté"); widths.append(12 * mm)
    if show_money:
        head += ["Montant", "Payé", "Reste"]; widths += [26 * mm, 26 * mm, 26 * mm]
    else:
        head.append("Émargement"); widths.append(40 * mm)
    widths[1] = width - sum(w for w in widths if w)
    data = [[Paragraph(h, st["head"]) for h in head]]
    for i, r in enumerate(rows, 1):
        line = [Paragraph(str(i), st["cell"]),
                Paragraph(escape(f"{r['student'].last_name} {r['student'].first_name}"), st["cell"]),
                Paragraph(escape(r["classe"].display_name), st["cell"])]
        if fee.allows_quantity:
            line.append(Paragraph(str(r["quantity"] or ""), st["cellr"]))
        if show_money:
            line += [Paragraph(_money(r["amount"], cur), st["cellr"]), Paragraph(_money(r["paid"], cur), st["cellr"]),
                     Paragraph(_money(r["reste"], cur), st["cellb"])]
        else:
            line.append("")
        data.append(line)
    t = _totals(rows)
    total = [Paragraph("", st["cell"]), Paragraph(f"<b>{t['count']} élève(s)</b>", st["cell"]), Paragraph("", st["cell"])]
    if fee.allows_quantity:
        total.append(Paragraph(f"<b>{t['quantity']}</b>", st["cellr"]))
    if show_money:
        total += [Paragraph(_money(t["total"], cur), st["cellb"]), Paragraph(_money(t["paid"], cur), st["cellb"]),
                  Paragraph(_money(t["rest"], cur), st["cellb"])]
    else:
        total.append("")
    data.append(total)
    story.append(_grid(data, widths, total_row=True))
    footer = lambda c, d: _draw_internal_footer(c, d, school)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return response
