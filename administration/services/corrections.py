"""Corrections réservées à la direction (Feedbacks V5, point 10).

Chaque correction est atomique, vérifie d'abord qu'elle ne casse rien, puis
laisse une ligne dans le journal des corrections (qui, quand, quoi, motif).
Règle générale : on ne supprime jamais de l'argent encaissé en silence. Une
facture ou une inscription qui porte des paiements ne peut être supprimée
qu'après l'annulation explicite de ces paiements.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import ProtectedError, Sum

from administration.models import CorrectionLog
from finance.models import FeeType, Invoice, Payment, StudentOption


def _reason(reason):
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise ValidationError("Indiquez le motif de la correction.")
    return reason


def _check_year_open(school_year):
    # Une année reprise (soldes antérieurs) reste corrigeable : ses reliquats se règlent aujourd'hui.
    if school_year.is_closed and not school_year.is_archive:
        raise ValidationError("Cette année scolaire est clôturée : aucune correction n'est possible.")


def _log(action, description, reason, user, *, student="", amount=None, receipt=""):
    return CorrectionLog.objects.create(
        action=action, description=description, reason=reason,
        user=user if getattr(user, "pk", None) else None,
        student_label=str(student)[:200], amount=amount, receipt_number=receipt or "",
    )


def _refresh_paid(invoice):
    invoice.paid_amount = invoice.payments.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    invoice.save(update_fields=["paid_amount"])


@transaction.atomic
def cancel_payment(payment, reason, user=None):
    reason = _reason(reason)
    invoice = payment.invoice
    enrollment = invoice.enrollment
    _check_year_open(enrollment.school_year)
    batch = payment.batch
    receipt = batch.receipt_number if batch else payment.receipt_number
    _log(
        CorrectionLog.Action.PAYMENT_CANCEL,
        f"Paiement {payment.receipt_number} du {payment.date:%d/%m/%Y} sur « {invoice.fee_type.name} »"
        f" ({enrollment.school_year.name}) annulé.",
        reason, user, student=enrollment.student, amount=payment.amount, receipt=payment.receipt_number,
    )
    payment.delete()
    _refresh_paid(invoice)
    if batch and not batch.payments.exists():
        # Le numéro du reçu groupé reste réservé grâce au journal.
        _log(CorrectionLog.Action.PAYMENT_CANCEL, f"Reçu groupé {receipt} entièrement annulé.",
             reason, user, student=enrollment.student, receipt=receipt)
        batch.delete()
    return invoice


@transaction.atomic
def delete_invoice(invoice, reason, user=None):
    reason = _reason(reason)
    enrollment = invoice.enrollment
    _check_year_open(enrollment.school_year)
    if invoice.payments.exists():
        raise ValidationError(
            "Cette facture porte déjà des paiements : annulez-les d'abord (chaque annulation est tracée)."
        )
    _log(CorrectionLog.Action.INVOICE_DELETE,
         f"Facture « {invoice.fee_type.name} » ({enrollment.school_year.name}, {invoice.total_amount:,.0f}) supprimée.".replace(",", " "),
         reason, user, student=enrollment.student, amount=invoice.total_amount)
    if invoice.fee_type.category == FeeType.Category.OPTIONAL:
        StudentOption.objects.filter(enrollment=enrollment, fee_type=invoice.fee_type).delete()
    invoice.delete()


def class_change_preview(enrollment, new_classe):
    """Effet d'un changement de classe sur la facturation : (à supprimer, à créer, bloquants)."""
    from finance.finance_signals import applicable_required_fees

    old = enrollment.classe
    enrollment.classe = new_classe
    try:
        target = {fee.id: fee for fee in applicable_required_fees(enrollment)}
    finally:
        enrollment.classe = old
    current = list(enrollment.invoices.exclude(fee_type__category=FeeType.Category.OPTIONAL).select_related("fee_type"))
    current_ids = {inv.fee_type_id for inv in current}
    to_delete = [inv for inv in current if inv.fee_type_id not in target]
    to_create = [fee for fid, fee in target.items() if fid not in current_ids]
    blocking = [inv for inv in to_delete if inv.paid_amount]
    return to_delete, to_create, blocking


@transaction.atomic
def change_enrollment_class(enrollment, new_classe, reason, user=None):
    reason = _reason(reason)
    _check_year_open(enrollment.school_year)
    if new_classe.school_year_id != enrollment.school_year_id:
        raise ValidationError("La nouvelle classe doit appartenir à la même année scolaire.")
    if new_classe.pk == enrollment.classe_id:
        raise ValidationError("L'élève est déjà dans cette classe.")
    level_changes = new_classe.education_level_id != enrollment.classe.education_level_id
    if level_changes and (enrollment.grades.exists() or enrollment.bulletin_item_results.exists()):
        raise ValidationError(
            "Des notes sont déjà saisies pour cet élève : le changement vers un autre niveau est impossible. "
            "Seul un changement de groupe du même niveau (ex. 10e A → 10e B) reste possible."
        )
    to_delete, to_create, blocking = class_change_preview(enrollment, new_classe)
    if blocking:
        names = ", ".join(inv.fee_type.name for inv in blocking)
        raise ValidationError(
            f"Les frais suivants, déjà payés, ne s'appliquent pas à la nouvelle classe : {names}. "
            "Annulez d'abord ces paiements, puis encaissez-les sur les frais de la nouvelle classe."
        )
    old_label = enrollment.classe.display_name
    for inv in to_delete:
        inv.delete()
    enrollment.classe = new_classe
    enrollment.save(update_fields=["classe"])
    for fee in to_create:
        Invoice.objects.get_or_create(enrollment=enrollment, fee_type=fee, defaults={"total_amount": fee.amount})
    detail = f"Classe {old_label} → {new_classe.display_name} ({enrollment.school_year.name})."
    if to_delete or to_create:
        detail += " Frais retirés : " + (", ".join(i.fee_type.name for i in to_delete) or "aucun")
        detail += " ; frais ajoutés : " + (", ".join(f.name for f in to_create) or "aucun") + "."
    _log(CorrectionLog.Action.CLASS_CHANGE, detail, reason, user, student=enrollment.student)
    return enrollment


def enrollment_blockers(enrollment):
    blockers = []
    if Payment.objects.filter(invoice__enrollment=enrollment).exists():
        blockers.append("des paiements sont enregistrés (annulez-les d'abord)")
    if enrollment.school_year.is_closed and not enrollment.school_year.is_archive:
        blockers.append("l'année scolaire est clôturée")
    if enrollment.promotion_proposals.exists() or hasattr(enrollment, "passage_decision_line"):
        blockers.append("une décision de passage existe déjà")
    return blockers


@transaction.atomic
def delete_enrollment(enrollment, reason, user=None):
    reason = _reason(reason)
    blockers = enrollment_blockers(enrollment)
    if blockers:
        raise ValidationError("Suppression impossible : " + " ; ".join(blockers) + ".")
    _log(CorrectionLog.Action.ENROLLMENT_DELETE,
         f"Inscription en {enrollment.classe.display_name} ({enrollment.school_year.name}) supprimée, "
         f"avec ses factures, notes et présences.",
         reason, user, student=enrollment.student)
    try:
        enrollment.delete()
    except ProtectedError:
        raise ValidationError("Suppression impossible : cette inscription est utilisée par une décision de passage.")


@transaction.atomic
def delete_student(student, reason, user=None):
    reason = _reason(reason)
    for enrollment in student.enrollments.all():
        blockers = enrollment_blockers(enrollment)
        if blockers:
            raise ValidationError(
                f"Suppression impossible ({enrollment.school_year.name}) : " + " ; ".join(blockers) + "."
            )
    label = f"{student} (matricule {student.matricule or '—'})"
    _log(CorrectionLog.Action.STUDENT_DELETE, f"Élève {label} supprimé avec toutes ses inscriptions.",
         reason, user, student=student)
    try:
        student.delete()
    except ProtectedError:
        raise ValidationError("Suppression impossible : cet élève est lié à une décision de passage.")
