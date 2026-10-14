"""Options élèves, dont les options à quantité et prix variables (uniformes…).

Bonne formule (Feedbacks V5, point 8) : UNE seule option « Uniforme » dans le
catalogue, cochée « Quantité et prix variables ». Au moment du choix, on
saisit le nombre d'uniformes et le prix unitaire (selon la taille) ; la
facture vaut quantité × prix. Inutile de créer « Uniforme petits »,
« Uniforme grands »… : les listes par option restent simples.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from finance.models import Invoice, StudentOption
from finance.services.grouped_payment import parse_amount


def read_quantity_price(data, fee, prefix="option"):
    """Lit ``option_qty_<id>`` et ``option_price_<id>`` (formulaires d'inscription et d'ajustement)."""
    if not fee.allows_quantity:
        return 1, None
    raw_qty = str(data.get(f"{prefix}_qty_{fee.id}") or "1").strip()
    try:
        quantity = int(raw_qty)
    except ValueError:
        raise ValidationError(f"Quantité invalide pour « {fee.name} ».")
    if quantity < 1 or quantity > 999:
        raise ValidationError(f"La quantité de « {fee.name} » doit être comprise entre 1 et 999.")
    price = parse_amount(data.get(f"{prefix}_price_{fee.id}"))
    if price is None:
        price = fee.amount
    if price <= 0:
        raise ValidationError(f"Le prix unitaire de « {fee.name} » doit être supérieur à zéro.")
    return quantity, price


@transaction.atomic
def add_option(enrollment, fee, quantity=1, unit_price=None):
    option = StudentOption.objects.filter(enrollment=enrollment, fee_type=fee).first()
    if option:
        return option
    if not fee.allows_quantity:
        quantity, unit_price = 1, None
    option = StudentOption(enrollment=enrollment, fee_type=fee, quantity=quantity, unit_price=unit_price)
    option.full_clean()
    option.save()  # le signal crée la facture : quantité × prix
    return option


@transaction.atomic
def update_option(option, quantity, unit_price):
    """Change la quantité ou le prix (ex. deux uniformes de plus) et met la facture à jour."""
    option.quantity, option.unit_price = quantity, unit_price
    invoice = Invoice.objects.select_for_update().filter(enrollment=option.enrollment, fee_type=option.fee_type).first()
    total = option.total
    if invoice and total < invoice.paid_amount:
        raise ValidationError(
            f"« {option.fee_type.name} » : le nouveau total ({total:,.0f}) est inférieur au montant déjà payé "
            f"({invoice.paid_amount:,.0f}).".replace(",", " ")
        )
    option.save(update_fields=["quantity", "unit_price"])
    if invoice:
        invoice.total_amount = total
        invoice.save(update_fields=["total_amount"])
    else:
        Invoice.objects.create(enrollment=option.enrollment, fee_type=option.fee_type, total_amount=total)
    return option
