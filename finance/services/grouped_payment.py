"""Encaissement groupé et regroupement par famille.

- ``family_enrollments`` : frères et sœurs inscrits la même année, reconnus
  par un numéro de téléphone de parent commun, ou par le même nom du père ET
  le même nom de la mère.
- ``record_grouped_payment`` : enregistre en une fois plusieurs règlements
  (une ligne par facture) sous un seul reçu.
"""
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from common.services.numbering_service import NumberingService
from finance.models import Invoice, Payment, PaymentBatch
from pedagogie.models import Enrollment


def _phone(value):
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("223") and len(digits) > 8:
        digits = digits[3:]  # indicatif du Mali
    return digits if len(digits) >= 8 else ""


def _name(value):
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(text.split())


def family_key_parts(student):
    phones = {_phone(student.father_phone), _phone(student.mother_phone), _phone(student.whatsapp_phone),
              _phone(getattr(student, "contact_phone", ""))} - {""}
    names = (_name(student.father_name), _name(student.mother_name))
    return phones, names if all(names) else None


def family_enrollments(enrollment):
    """Inscriptions de la même année appartenant à la même famille (l'élève compris)."""
    phones, names = family_key_parts(enrollment.student)
    found = [enrollment]
    if not phones and not names:
        return found
    candidates = (
        Enrollment.objects.filter(school_year=enrollment.school_year).exclude(pk=enrollment.pk)
        .select_related("student", "classe")
    )
    for other in candidates:
        other_phones, other_names = family_key_parts(other.student)
        if (phones & other_phones) or (names and other_names == names):
            found.append(other)
    return sorted(found, key=lambda e: (e.pk != enrollment.pk, e.student.last_name, e.student.first_name))


def group_families(enrollments):
    """Regroupe des inscriptions (même année) en familles.

    Même règle que ``family_enrollments`` (téléphone commun, ou mêmes noms du
    père ET de la mère), appliquée de proche en proche : si A et B partagent un
    téléphone et B et C les mêmes noms, A, B et C forment une seule famille.
    """
    enrollments = list(enrollments)
    parent = list(range(len(enrollments)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner = {}
    for index, enrollment in enumerate(enrollments):
        phones, names = family_key_parts(enrollment.student)
        keys = [("tel", p) for p in phones] + ([("noms", names)] if names else [])
        for key in keys:
            if key in owner:
                parent[find(index)] = find(owner[key])
            else:
                owner[key] = index
    groups = {}
    for index, enrollment in enumerate(enrollments):
        groups.setdefault(find(index), []).append(enrollment)
    return [sorted(g, key=lambda e: (e.student.last_name.lower(), e.student.first_name.lower())) for g in groups.values()]


def family_label(members):
    """Nom affiché d'une famille : la personne de contact (à défaut le père, puis la mère)."""
    for m in members:
        if m.student.responsible_name:
            return m.student.responsible_label
    return f"Famille {members[0].student.last_name}"


def family_phone(members):
    for m in members:
        if m.student.responsible_phone:
            return m.student.responsible_phone
    return ""


CATEGORY_ORDER = {"registration": 0, "reenrollment": 1, "tuition": 2, "optional": 3, "arrears": 4}


def payment_priority(invoice, current_year_id):
    """Ordre d'imputation d'un versement (V5-12).

    1. l'année en cours d'abord (inscription, scolarité, options) ;
    2. puis les dettes des années passées, année par année, de la plus ancienne
       à la plus récente (les arriérés « année non précisée » en premier, car
       ils sont au moins aussi anciens que tout le reste).
    """
    from finance.services.arrears import is_unspecified

    year = invoice.enrollment.school_year
    if year.pk == current_year_id:
        bucket = (0, 0, 0)
    else:
        bucket = (1, 0 if is_unspecified(invoice) else 1, year.start_date.toordinal())
    return bucket + (CATEGORY_ORDER.get(invoice.fee_type.category, 9), invoice.fee_type.name,
                     invoice.enrollment.student.last_name, invoice.enrollment.student.first_name)


def sort_by_priority(invoices, current_year_id):
    return sorted(invoices, key=lambda inv: payment_priority(inv, current_year_id))


def open_invoices(enrollments):
    return list(
        Invoice.objects.filter(enrollment__in=enrollments, paid_amount__lt=F("total_amount"))
        .select_related("enrollment__student", "enrollment__classe", "enrollment__school_year", "fee_type")
        .order_by("enrollment__student__last_name", "enrollment__student__first_name",
                  "enrollment__school_year__start_date", "fee_type__name")
    )


def parse_amount(raw):
    text = re.sub(r"[\s ]", "", str(raw or "")).replace(",", ".")
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValidationError(f"Montant invalide : « {raw} ».")
    if value != value.to_integral_value():
        raise ValidationError(f"Montant invalide : « {raw} » (pas de centimes).")
    return value


def _split(line):
    """(facture, montant) ou (facture, montant, [(poste, montant)])."""
    invoice, amount = line[0], line[1]
    return invoice, amount, (line[2] if len(line) > 2 else None)


@transaction.atomic
def record_carryover(lines, date, comment="", user=None):
    """Reprise de versements déjà reçus sur papier avant KIS (aucun reçu édité).

    Chaque ligne garde sa date d'origine et un numéro « REPRISE-… » qui n'entre
    pas dans la numérotation des reçus.
    """
    import uuid
    import datetime as _dt

    lines = [_split(line) for line in lines]
    lines = [(invoice, amount, alloc) for invoice, amount, alloc in lines if amount]
    if not lines:
        raise ValidationError("Cochez au moins une facture et indiquez le montant déjà versé.")
    if date is None:
        raise ValidationError("Indiquez la date du versement d'origine.")
    if date > _dt.date.today():
        raise ValidationError("La date d'un versement repris ne peut pas être dans le futur.")
    errors = []
    for invoice, amount, alloc in lines:
        invoice.refresh_from_db()
        if amount <= 0 or amount > invoice.reste:
            errors.append(f"{invoice.enrollment.student} — {invoice.fee_type.name} : montant invalide ou supérieur au reste à payer.")
        elif alloc:
            from finance.services.components import _check
            try:
                _check(invoice, alloc, expected=amount)
            except ValidationError as exc:
                errors.extend(exc.messages)
    if errors:
        raise ValidationError(errors)
    note = ("Reprise : versement reçu avant KIS. " + comment.strip()).strip()
    created = []
    for invoice, amount, alloc in lines:
        payment = Payment(invoice=invoice, amount=amount, is_carryover=True, comment=note,
                          receipt_number=f"REPRISE-{uuid.uuid4().hex[:10].upper()}")
        payment._allocations = alloc or None
        payment.save()
        Payment.objects.filter(pk=payment.pk).update(date=date)
        created.append(payment)
    return created


@transaction.atomic
def record_grouped_payment(lines, payer_name="", comment="", user=None):
    """``lines`` : [(facture, montant)] ou [(facture, montant, ventilation)].

    ``ventilation`` : [(poste, montant)] pour une facture détaillée en postes
    (inscription, manuel, uniformes…) ; à défaut, le montant est réparti dans
    l'ordre des postes. Retourne le PaymentBatch créé (un seul reçu global).
    Tout est enregistré ou rien : une ligne invalide annule l'ensemble.
    """
    from finance.services.components import _check
    lines = [_split(line) for line in lines]
    lines = [(invoice, amount, alloc) for invoice, amount, alloc in lines if amount]
    if not lines:
        raise ValidationError("Cochez au moins une facture et indiquez le montant versé.")
    errors = []
    for invoice, amount, alloc in lines:
        invoice.refresh_from_db()
        label = f"{invoice.enrollment.student} — {invoice.fee_type.name}"
        if amount <= 0:
            errors.append(f"{label} : le montant doit être supérieur à zéro.")
        elif amount > invoice.reste:
            errors.append(f"{label} : {amount:,.0f} dépasse le reste à payer ({invoice.reste:,.0f}).".replace(",", " "))
        elif alloc:
            try:
                _check(invoice, alloc, expected=amount)
            except ValidationError as exc:
                errors.extend(f"{label} — {m}" for m in exc.messages)
    if errors:
        raise ValidationError(errors)
    batch = PaymentBatch.objects.create(
        receipt_number=NumberingService.next_receipt_number(), payer_name=payer_name.strip()[:150],
        comment=comment.strip(), created_by=user if getattr(user, "pk", None) else None,
    )
    for index, (invoice, amount, alloc) in enumerate(lines, 1):
        payment = Payment(invoice=invoice, amount=amount, batch=batch, comment=comment.strip() or None,
                          receipt_number=f"{batch.receipt_number}/{index}")
        payment._allocations = alloc or None
        payment.save()
    return batch
