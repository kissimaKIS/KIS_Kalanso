from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction

from finance.models import DiscountAllocation, EnrollmentDiscount, Invoice


def apply_enrollment_discount(enrollment, discount_type, value, reason, note=""):
    value = Decimal(str(value))
    invoices = list(Invoice.objects.filter(enrollment=enrollment).order_by("id"))
    gross = sum((invoice.total_amount for invoice in invoices), Decimal("0"))
    if gross <= 0:
        raise ValidationError("Aucun montant facturable ne permet d'appliquer une remise.")
    if value <= 0:
        raise ValidationError("La valeur de la remise doit être supérieure à zéro.")
    if discount_type == EnrollmentDiscount.DiscountType.PERCENTAGE:
        if value > 100:
            raise ValidationError("Une remise en pourcentage ne peut pas dépasser 100 %.")
        amount = (gross * value / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    elif discount_type == EnrollmentDiscount.DiscountType.FIXED:
        amount = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    else:
        raise ValidationError("Type de remise invalide.")
    if amount > gross:
        raise ValidationError("La remise ne peut pas dépasser le montant total à payer.")
    if not reason.strip():
        raise ValidationError("Le motif de la remise est obligatoire.")

    with transaction.atomic():
        discount = EnrollmentDiscount.objects.create(
            enrollment=enrollment, discount_type=discount_type, value=value,
            amount=amount, reason=reason.strip(), note=note.strip(),
        )
        remaining = amount
        for invoice in invoices:
            if remaining <= 0:
                break
            applied = min(invoice.total_amount, remaining)
            if applied <= 0:
                continue
            DiscountAllocation.objects.create(
                discount=discount, invoice=invoice,
                original_amount=invoice.total_amount, discount_amount=applied,
            )
            invoice.total_amount -= applied
            invoice.save(update_fields=["total_amount"])
            remaining -= applied
    return discount
