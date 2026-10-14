"""Postes d'un frais (inscription + manuel + uniformes…) et ventilation des versements."""
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from finance.models import FeeType, Invoice
from finance.services import components as svc
from finance.services.grouped_payment import parse_amount


def _rows_from_post(post):
    rows, errors = [], []
    for index in range(int(post.get("rows") or 0) + 3):
        name = post.get(f"name_{index}", "")
        if post.get(f"delete_{index}"):
            continue
        try:
            amount = parse_amount(post.get(f"amount_{index}"))
        except ValidationError as exc:
            errors.extend(exc.messages)
            continue
        pk = post.get(f"id_{index}") or None
        if name.strip() or amount:
            rows.append((int(pk) if pk else None, name, amount))
    return rows, errors


@login_required
def fee_components(request, fee_id):
    fee = get_object_or_404(FeeType.objects.select_related("school_year__school"), pk=fee_id)
    errors = []
    if request.method == "POST":
        action = request.POST.get("action", "save")
        if action == "apply":
            report = svc.apply_components_to_existing(fee)
            parts = []
            if report["created"] or report["rebuilt"]:
                parts.append(f"{report['created'] + report['rebuilt']} facture(s) détaillée(s)")
            if report["kept"]:
                parts.append(f"{report['kept']} déjà ventilée(s) laissée(s) telle(s) quelle(s)")
            if report["removed"]:
                parts.append(f"détail retiré de {report['removed']} facture(s)")
            if report["to_ventilate"]:
                parts.append(f"{report['to_ventilate']} versement(s) partiel(s) à ventiler (voir la liste ci-dessous)")
            messages.success(request, "Postes appliqués aux inscriptions existantes : " + (", ".join(parts) or "aucune facture concernée") + ".")
            return redirect("fee_components", fee_id=fee.id)
        rows, errors = _rows_from_post(request.POST)
        if not errors:
            try:
                svc.save_components(fee, rows)
            except ValidationError as exc:
                errors.extend(exc.messages)
            else:
                existing = Invoice.objects.filter(fee_type=fee).count()
                msg = "Postes enregistrés. Le montant du frais est maintenant la somme des postes."
                if existing:
                    msg += f" {existing} facture(s) existent déjà pour ce frais : cliquez sur « Appliquer aux inscriptions existantes »."
                messages.success(request, msg)
                return redirect("fee_components", fee_id=fee.id)
    comps = list(fee.components.all())
    invoices = Invoice.objects.filter(fee_type=fee)
    detailed = invoices.filter(lines__isnull=False).distinct().count()
    return render(request, "finance/fee_types/components.html", {
        "fee": fee, "components": comps, "blank_rows": range(len(comps), len(comps) + 3), "rows": len(comps),
        "errors": errors, "currency": fee.school_year.school.currency,
        "invoice_count": invoices.count(), "detailed_count": detailed,
        "to_ventilate": svc.invoices_to_ventilate(fee=fee),
    })


@login_required
def invoice_ventilation(request, invoice_id):
    invoice = get_object_or_404(Invoice.objects.select_related("enrollment__student", "enrollment__classe", "fee_type",
                                                               "enrollment__school_year__school"), pk=invoice_id)
    lines = list(invoice.lines.all())
    available = svc.unallocated(invoice)
    errors = []
    if request.method == "POST":
        amounts = {}
        for line in lines:
            try:
                amounts[line] = parse_amount(request.POST.get(f"line_{line.id}")) or Decimal("0")
            except ValidationError as exc:
                errors.extend(exc.messages)
        if not errors:
            try:
                svc.ventilate(invoice, amounts)
            except ValidationError as exc:
                errors.extend(exc.messages)
            else:
                left = svc.unallocated(invoice)
                messages.success(request, "Ventilation enregistrée." + (
                    f" Il reste {left:,.0f} à ventiler.".replace(",", " ") if left else ""))
                return redirect("student_detail", student_id=invoice.enrollment.student_id)
    proposal = svc.suggest_in_order(invoice)
    for line in lines:
        line.proposal = proposal.get(line.pk, Decimal("0"))
        line.value = request.POST.get(f"line_{line.id}", "") if request.method == "POST" else ""
    return render(request, "finance/invoices/ventilation.html", {
        "invoice": invoice, "lines": lines, "available": available, "errors": errors,
        "currency": invoice.enrollment.school_year.school.currency,
        "payments": invoice.payments.order_by("date", "id"),
    })
