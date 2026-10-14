from django.db.models.signals import post_save
from django.dispatch import receiver

from administration.models import OtherPersonnelPayment, TeacherPayment
from pilotage.models import BudgetCategory, BudgetEntry


def _register_salary_expense(payment, person_name, personnel_label):
    """Create the corresponding budget expense once a salary payment is recorded."""
    category, _ = BudgetCategory.objects.get_or_create(name="Salaires", defaults={"is_active": True})
    BudgetEntry.objects.create(
        school_year=payment.school_year,
        category=category,
        kind="EXPENSE",
        label=f"Salaire {personnel_label} — {person_name} — {payment.period}",
        amount=payment.amount,
        date=payment.paid_at,
        notes=payment.note or "",
    )


@receiver(post_save, sender=TeacherPayment)
def teacher_payment_to_budget(sender, instance, created, **kwargs):
    if not created:
        return
    _register_salary_expense(
        instance,
        instance.teacher.full_name or str(instance.teacher),
        "enseignant",
    )


@receiver(post_save, sender=OtherPersonnelPayment)
def other_personnel_payment_to_budget(sender, instance, created, **kwargs):
    if not created:
        return
    _register_salary_expense(
        instance,
        str(instance.personnel),
        "personnel",
    )
