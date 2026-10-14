from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver

from pedagogie.models import Enrollment
from .models import FeeType, Invoice, StudentOption


def _is_reenrollment(instance):
    return Enrollment.objects.filter(
        student_id=instance.student_id,
        school_year__start_date__lt=instance.school_year.start_date,
    ).exists()


def _cycle_registration_already_billed(instance, fee):
    return Invoice.objects.filter(
        enrollment__student_id=instance.student_id,
        fee_type__category=FeeType.Category.REGISTRATION,
        fee_type__registration_scope=FeeType.RegistrationScope.CYCLE,
        fee_type__cycle_key=fee.cycle_key,
        enrollment__school_year__school_id=instance.school_year.school_id,
    ).exists()


def applicable_required_fees(instance):
    """Frais obligatoires dus par une inscription selon sa classe (hors options)."""
    reenrollment = _is_reenrollment(instance)
    fees = FeeType.objects.filter(
        Q(classe=instance.classe)
        | Q(classe__isnull=True, education_level=instance.classe.education_level)
        | Q(classe__isnull=True, education_level__isnull=True, school_type=instance.classe.education_level.school_type)
        | Q(classe__isnull=True, education_level__isnull=True, school_type__isnull=True),
        school_year=instance.school_year,
        is_required=True,
        is_active=True,
    )
    result = []
    for fee in fees:
        if fee.category == FeeType.Category.OPTIONAL:
            continue
        if fee.category == FeeType.Category.REENROLLMENT and not reenrollment:
            continue
        if fee.category == FeeType.Category.REGISTRATION:
            if fee.registration_scope == FeeType.RegistrationScope.CYCLE and Invoice.objects.filter(
                enrollment__student_id=instance.student_id,
                fee_type__category=FeeType.Category.REGISTRATION,
                fee_type__registration_scope=FeeType.RegistrationScope.CYCLE,
                fee_type__cycle_key=fee.cycle_key,
                enrollment__school_year__school_id=instance.school_year.school_id,
            ).exclude(enrollment_id=instance.pk, fee_type=fee).exists():
                continue
        result.append(fee)
    return result


@receiver(post_save, sender=Enrollment)
def create_invoices_for_enrollment(sender, instance, created, **kwargs):
    if not created:
        return
    for fee in applicable_required_fees(instance):
        Invoice.objects.get_or_create(
            enrollment=instance,
            fee_type=fee,
            defaults={"total_amount": fee.amount},
        )


@receiver(post_save, sender=StudentOption)
def create_invoice_for_option(sender, instance, created, **kwargs):
    if not created:
        return
    Invoice.objects.get_or_create(
        enrollment=instance.enrollment,
        fee_type=instance.fee_type,
        defaults={"total_amount": instance.total},
    )


# ---------------------------------------------------------------- postes des frais (09/10)
from django.db.models.signals import post_delete  # noqa: E402

from .models import InvoiceLine, Payment, PaymentAllocation  # noqa: E402


@receiver(post_save, sender=Invoice)
def sync_invoice_lines(sender, instance, created, update_fields=None, **kwargs):
    from finance.services import components
    if kwargs.get("raw"):
        return
    if created:
        components.build_lines(instance)
        return
    if update_fields is not None and set(update_fields) <= {"paid_amount"}:
        return
    if instance.lines.exists():
        components.fit_lines(instance)


@receiver(post_save, sender=Payment)
def allocate_payment_to_lines(sender, instance, created, **kwargs):
    """Ventile un nouveau paiement sur les postes : selon le choix de l'utilisateur
    (``payment._allocations``), sinon dans l'ordre des postes."""
    from finance.services import components
    if not created or kwargs.get("raw") or getattr(instance, "_skip_allocation", False):
        return
    if not instance.invoice.lines.exists():
        return
    chosen = getattr(instance, "_allocations", None)
    if chosen:
        components.allocate(instance, chosen)
    else:
        components.auto_allocate(instance)


@receiver(post_delete, sender=PaymentAllocation)
def refresh_line_after_allocation_delete(sender, instance, **kwargs):
    from django.db.models import Sum
    paid = PaymentAllocation.objects.filter(line_id=instance.line_id).aggregate(t=Sum("amount"))["t"] or 0
    InvoiceLine.objects.filter(pk=instance.line_id).update(paid_amount=paid)
