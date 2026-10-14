"""Fusion de deux fiches élève (doublons créés par un import incomplet).

La fiche gardée récupère tout ce qui était rattaché à l'autre : inscriptions,
factures, paiements, options, notes, présences, discipline, documents. Ses
cases vides sont complétées ; ses informations déjà remplies ne sont jamais
écrasées. L'autre fiche est ensuite supprimée et la fusion est inscrite au
journal des corrections.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum

from administration.models import CorrectionLog
from administration.services.student_matching import COMPLETABLE_FIELDS, FIELD_LABELS, comparable


def merge_preview(keep, drop):
    """Ce que la fusion va faire, et ce qui l'empêche."""
    blockers, lines = [], []
    if keep.pk == drop.pk:
        blockers.append("il s'agit de la même fiche")
    keep_years = {e.school_year_id: e for e in keep.enrollments.select_related("classe", "school_year")}
    for e in drop.enrollments.select_related("classe", "school_year"):
        other = keep_years.get(e.school_year_id)
        if other and other.classe_id != e.classe_id:
            blockers.append(
                f"{e.school_year.name} : les deux fiches sont inscrites dans deux classes différentes "
                f"({other.classe.display_name} et {e.classe.display_name}). Changez d'abord la classe de l'une d'elles."
            )
        elif other:
            lines.append(f"{e.school_year.name} : les deux inscriptions en {e.classe.display_name} sont réunies "
                         "(factures, paiements, notes et présences).")
        else:
            lines.append(f"{e.school_year.name} : l'inscription en {e.classe.display_name} passe sur la fiche gardée.")
    fills = [f for f in COMPLETABLE_FIELDS
             if comparable(f, getattr(keep, f)) is None and comparable(f, getattr(drop, f)) is not None]
    if fills:
        lines.append("Cases complétées : " + ", ".join(FIELD_LABELS[f] for f in fills) + ".")
    kept_values = [f for f in COMPLETABLE_FIELDS
                   if comparable(f, getattr(keep, f)) is not None and comparable(f, getattr(drop, f)) is not None
                   and comparable(f, getattr(keep, f)) != comparable(f, getattr(drop, f))]
    if kept_values:
        lines.append("Valeurs différentes, celles de la fiche gardée sont conservées : "
                     + ", ".join(FIELD_LABELS[f] for f in kept_values) + ".")
    if not keep.photo and drop.photo:
        lines.append("La photo de l'autre fiche est reprise.")
    docs = drop.documents.count()
    if docs:
        lines.append(f"{docs} document(s) rattaché(s) à la fiche gardée.")
    return lines, blockers


def _move_rows(queryset, field, target, on_conflict=None):
    """Déplace des lignes vers ``target`` ; en cas de doublon (contrainte d'unicité), la ligne
    de la fiche gardée l'emporte et ``on_conflict`` décide du sort de l'autre (par défaut : supprimée)."""
    for obj in list(queryset):
        try:
            with transaction.atomic():
                # update() direct : certaines lignes (présences…) refusent d'être « modifiées » par save().
                type(obj).objects.filter(pk=obj.pk).update(**{field: target})
        except IntegrityError:
            obj.refresh_from_db()
            if on_conflict:
                on_conflict(obj)
            else:
                obj.delete()


def _merge_enrollment(keep_e, drop_e):
    from finance.models import EnrollmentDiscount, Invoice, Payment

    def invoice_conflict(inv):
        target = Invoice.objects.get(enrollment=keep_e, fee_type=inv.fee_type)
        moved = False
        for payment in inv.payments.all():
            Payment.objects.filter(pk=payment.pk).update(invoice=target)
            moved = True
        if moved:
            paid = target.payments.aggregate(t=Sum("amount"))["t"] or Decimal("0")
            target.paid_amount = paid
            if paid > target.total_amount:
                target.total_amount = paid  # double paiement : rien n'est perdu, à régulariser
            target.save(update_fields=["paid_amount", "total_amount"])
        inv.delete()

    for rel in type(drop_e)._meta.related_objects:
        model, field = rel.related_model, rel.field.name
        qs = model.objects.filter(**{field: drop_e})
        if model is Invoice:
            _move_rows(qs, field, keep_e, invoice_conflict)
        elif rel.one_to_one:
            if model is EnrollmentDiscount and EnrollmentDiscount.objects.filter(enrollment=keep_e).exists():
                qs.delete()
            else:
                _move_rows(qs, field, keep_e)
        else:
            _move_rows(qs, field, keep_e)
    drop_e.delete()


@transaction.atomic
def merge_students(keep, drop, reason, user=None):
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise ValidationError("Indiquez le motif de la fusion.")
    lines, blockers = merge_preview(keep, drop)
    if blockers:
        raise ValidationError("Fusion impossible : " + " ".join(blockers))
    keep_years = {e.school_year_id: e for e in keep.enrollments.all()}
    for e in list(drop.enrollments.all()):
        target = keep_years.get(e.school_year_id)
        if target:
            _merge_enrollment(target, e)
        else:
            type(e).objects.filter(pk=e.pk).update(student=keep)
    drop.documents.update(student=keep)
    # Compléter les cases vides (le matricule est libéré d'abord : il est unique).
    fills = {f: getattr(drop, f) for f in COMPLETABLE_FIELDS
             if comparable(f, getattr(keep, f)) is None and comparable(f, getattr(drop, f)) is not None}
    photo = drop.photo if (not keep.photo and drop.photo) else None
    label = f"{drop.last_name} {drop.first_name}" + (f" (matricule {drop.matricule})" if drop.matricule else "")
    drop_id = drop.pk
    type(drop).objects.filter(pk=drop_id).update(matricule=None)
    for f, value in fills.items():
        setattr(keep, f, value)
    if photo:
        keep.photo = photo.name
    keep.save()
    type(drop).objects.filter(pk=drop_id).delete()
    CorrectionLog.objects.create(
        action=CorrectionLog.Action.STUDENT_MERGE,
        description=f"Fiche {label} (n° {drop_id}) fusionnée dans {keep} (n° {keep.pk}). " + " ".join(lines),
        reason=reason, user=user if getattr(user, "pk", None) else None, student_label=str(keep)[:200],
    )
    return keep
