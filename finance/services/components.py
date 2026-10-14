"""Composantes d'un frais (retours du 09/10).

Un frais reste unique et global pour la famille (ex. « Inscription
préscolaire » 20 000 F, un seul reçu) mais il est détaillé en interne en
postes (inscription, manuel, 2 uniformes…).

- Chaque facture de ce frais reçoit ses propres postes (``InvoiceLine``),
  copiés des composantes du frais.
- Chaque paiement est ventilé sur les postes réglés (``PaymentAllocation``) :
  le payé d'un poste = la somme de ses ventilations.
- Les paiements reçus avant la mise en place des postes ne sont jamais
  modifiés : leur montant reste « à ventiler » tant que l'utilisateur ne l'a
  pas réparti (sauf facture entièrement soldée : la répartition est alors
  évidente et faite automatiquement).
- Si le total de la facture change (remise, ajustement), le premier poste
  absorbe la différence (il s'agit en général des frais de dossier de
  l'école ; les articles comme les manuels et uniformes gardent leur prix).
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from finance.models import FeeComponent, Invoice, InvoiceLine, Payment, PaymentAllocation

ZERO = Decimal("0")


def _money(value):
    return f"{value:,.0f}".replace(",", " ")


# ---------------------------------------------------------------- postes d'une facture
def has_lines(invoice):
    return invoice.lines.exists()


def fit_lines(invoice):
    """Aligne la somme des postes sur le total de la facture (le premier poste absorbe l'écart)."""
    lines = list(invoice.lines.all())
    if not lines:
        return
    diff = invoice.total_amount - sum((l.amount for l in lines), ZERO)
    if diff == 0:
        return
    if diff > 0:
        lines[0].amount += diff
        lines[0].save(update_fields=["amount"])
        return
    to_remove = -diff
    # D'abord sans descendre sous ce qui est déjà payé, puis jusqu'à zéro si nécessaire.
    for floor_paid in (True, False):
        for line in lines:
            if to_remove <= 0:
                break
            floor = line.paid_amount if floor_paid else ZERO
            cut = min(to_remove, max(ZERO, line.amount - floor))
            if cut:
                line.amount -= cut
                line.save(update_fields=["amount"])
                to_remove -= cut


def build_lines(invoice):
    """Crée les postes d'une facture à partir des composantes de son frais (si elle n'en a pas)."""
    if invoice.lines.exists():
        return False
    components = list(invoice.fee_type.components.all())
    if not components:
        return False
    InvoiceLine.objects.bulk_create([
        InvoiceLine(invoice=invoice, component=c, name=c.name, amount=c.amount, order=index)
        for index, c in enumerate(components)
    ])
    fit_lines(invoice)
    if invoice.paid_amount and invoice.paid_amount >= invoice.total_amount:
        settle_paid_invoice(invoice)
    return True


def refresh_line(line):
    paid = line.allocations.aggregate(total=Sum("amount"))["total"] or ZERO
    if paid != line.paid_amount:
        line.paid_amount = paid
        line.save(update_fields=["paid_amount"])


def allocated_total(invoice):
    return InvoiceLine.objects.filter(invoice=invoice).aggregate(total=Sum("paid_amount"))["total"] or ZERO


def unallocated(invoice):
    """Montant déjà payé sur la facture mais pas encore réparti sur les postes."""
    if not invoice.lines.exists():
        return ZERO
    return max(ZERO, invoice.paid_amount - allocated_total(invoice))


def payment_unallocated(payment):
    done = payment.allocations.aggregate(total=Sum("amount"))["total"] or ZERO
    return max(ZERO, payment.amount - done)


# ---------------------------------------------------------------- ventilation d'un paiement
def _check(invoice, allocations, expected=None):
    lines = {l.pk: l for l in invoice.lines.all()}
    total = ZERO
    for line, amount in allocations:
        if line.pk not in lines:
            raise ValidationError(f"Le poste « {line.name} » n'appartient pas à cette facture.")
        if amount < 0:
            raise ValidationError(f"{line.name} : montant négatif.")
        if amount > lines[line.pk].reste:
            raise ValidationError(f"{line.name} : {_money(amount)} dépasse le reste du poste ({_money(lines[line.pk].reste)}).")
        total += amount
    if expected is not None and total != expected:
        raise ValidationError(f"La répartition sur les postes ({_money(total)}) doit être égale au montant versé ({_money(expected)}).")
    return total


def allocate(payment, allocations):
    """``allocations`` : [(poste, montant)] ; la somme doit être égale au paiement."""
    allocations = [(line, amount) for line, amount in allocations if amount]
    _check(payment.invoice, allocations, expected=payment.amount)
    for line, amount in allocations:
        PaymentAllocation.objects.create(payment=payment, line=line, amount=amount)
        refresh_line(line)


def auto_allocate(payment):
    """Répartit un paiement sur les postes, dans l'ordre, jusqu'à épuisement."""
    left = payment_unallocated(payment)
    for line in payment.invoice.lines.all():
        if left <= 0:
            break
        part = min(left, line.reste)
        if part > 0:
            PaymentAllocation.objects.create(payment=payment, line=line, amount=part)
            refresh_line(line)
            left -= part


def suggest_in_order(invoice, amount=None):
    """Proposition de ventilation dans l'ordre des postes (pour pré-remplir un formulaire)."""
    left = unallocated(invoice) if amount is None else amount
    result = {}
    for line in invoice.lines.all():
        part = min(left, line.reste)
        result[line.pk] = part
        left -= part
    return result


@transaction.atomic
def ventilate(invoice, amounts):
    """Ventile l'argent déjà reçu (non réparti) d'une facture.

    ``amounts`` : {poste: montant}. Les montants sont imputés sur les paiements
    non encore répartis, du plus ancien au plus récent. Les paiements eux-mêmes
    (montant, date, reçu) ne changent pas.
    """
    allocations = [(line, amount) for line, amount in amounts.items() if amount]
    total = _check(invoice, allocations)
    available = unallocated(invoice)
    if total > available:
        raise ValidationError(f"Vous répartissez {_money(total)} alors que seulement {_money(available)} restent à ventiler.")
    payments = [(p, payment_unallocated(p)) for p in invoice.payments.order_by("date", "id")]
    payments = [[p, free] for p, free in payments if free > 0]
    for line, amount in allocations:
        need = amount
        for slot in payments:
            if need <= 0:
                break
            take = min(need, slot[1])
            if take > 0:
                PaymentAllocation.objects.create(payment=slot[0], line=line, amount=take)
                slot[1] -= take
                need -= take
        refresh_line(line)


def settle_paid_invoice(invoice):
    """Facture soldée : chaque poste est forcément réglé en entier ; on ventile sans demander."""
    if unallocated(invoice) <= 0:
        return
    ventilate(invoice, {line: line.reste for line in invoice.lines.all() if line.reste > 0})


# ---------------------------------------------------------------- composantes d'un frais
@transaction.atomic
def save_components(fee, rows):
    """``rows`` : [(id ou None, nom, montant)] dans l'ordre voulu. Le montant du frais devient la somme."""
    if fee.allows_quantity:
        raise ValidationError("Un frais à quantité variable (ex. uniformes à l'unité) ne peut pas être détaillé en postes.")
    clean = []
    for pk, name, amount in rows:
        name = (name or "").strip()
        if not name and not amount:
            continue
        if not name:
            raise ValidationError("Chaque poste doit avoir un nom.")
        if amount is None or amount <= 0:
            raise ValidationError(f"{name} : le montant doit être supérieur à zéro.")
        clean.append((pk, name[:100], amount))
    keep = []
    for order, (pk, name, amount) in enumerate(clean):
        comp = fee.components.filter(pk=pk).first() if pk else None
        if comp is None:
            comp = FeeComponent(fee_type=fee)
        comp.name, comp.amount, comp.order = name, amount, order
        comp.save()
        keep.append(comp.pk)
    fee.components.exclude(pk__in=keep).delete()
    if clean:
        total = sum((a for _, _, a in clean), ZERO)
        if total != fee.amount:
            fee.amount = total
            fee.save(update_fields=["amount"])
    return fee.components.all()


@transaction.atomic
def apply_components_to_existing(fee):
    """Applique les postes du frais aux factures déjà créées.

    - facture sans postes : postes créés ;
    - facture dont les postes n'ont encore reçu aucun paiement : postes recréés
      avec la nouvelle composition ;
    - facture dont des postes ont déjà reçu de l'argent : laissée telle quelle.
    Les paiements ne sont jamais modifiés. Une facture soldée est ventilée
    automatiquement ; une facture partiellement payée reste « à ventiler ».
    """
    components = list(fee.components.all())
    report = {"created": 0, "rebuilt": 0, "kept": 0, "removed": 0, "to_ventilate": 0}
    for invoice in Invoice.objects.filter(fee_type=fee).select_related("fee_type"):
        lines = invoice.lines.all()
        if lines.exists():
            if PaymentAllocation.objects.filter(line__invoice=invoice).exists():
                report["kept"] += 1
            else:
                lines.delete()
                if components:
                    build_lines(invoice)
                    report["rebuilt"] += 1
                else:
                    report["removed"] += 1
        elif components:
            build_lines(invoice)
            report["created"] += 1
        if components and invoice.paid_amount and invoice.paid_amount >= invoice.total_amount:
            settle_paid_invoice(invoice)
        if unallocated(invoice) > 0:
            report["to_ventilate"] += 1
    return report


def invoices_to_ventilate(fee=None, school_year=None):
    qs = Invoice.objects.filter(lines__isnull=False, paid_amount__gt=0).distinct()
    if fee is not None:
        qs = qs.filter(fee_type=fee)
    if school_year is not None:
        qs = qs.filter(enrollment__school_year=school_year)
    qs = qs.select_related("enrollment__student", "enrollment__classe", "fee_type")
    result = []
    for inv in qs:
        inv.to_ventilate = unallocated(inv)
        if inv.to_ventilate > 0:
            result.append(inv)
    return result
