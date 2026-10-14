"""États de salaires (FeedbacksV2, point 2).

Deux écrans pensés pour remplacer la saisie « un mois à la fois » :

- ``permanent_annual_statement`` : une grille (personnel permanent × mois de
  l'année scolaire) pour enregistrer plusieurs salaires fixes en une seule
  fois, préremplie avec le salaire mensuel de chaque personne.
- ``hourly_monthly_statement`` : pour un mois donné, un état par personne
  payée à l'heure (enseignants vacataires + autre personnel), avec un
  montant suggéré calculé automatiquement à partir des présences pointées
  (heures d'entrée/sortie), modifiable avant validation.

Aucun des deux écrans ne remplace la saisie individuelle existante
(``teacher_payment_create`` / ``other_personnel_payment_create``), qui reste
disponible pour un cas particulier ou une correction ponctuelle.
"""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render

from administration.models import SchoolYear, Teacher, OtherPersonnel, TeacherPayment, OtherPersonnelPayment
from vie_scolaire.models import TeacherAttendance, OtherPersonnelAttendance
from common.years import viewed_year

MONTHS_FR = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]


def _school_year_periods(year):
    """Liste des mois (avec leurs bornes) couverts par une année scolaire.

    Chaque élément : {"index": int, "label": "Mois AAAA", "start": date, "end": date}.
    Le libellé est exactement au format déjà utilisé par la saisie manuelle
    (aide du formulaire : « Ex. Septembre 2026 »), pour que les deux modes de
    saisie partagent la même période sans créer de doublon.
    """
    if not year or not year.start_date or not year.end_date:
        return []
    periods = []
    cursor = date(year.start_date.year, year.start_date.month, 1)
    index = 0
    while cursor <= year.end_date:
        if cursor.month == 12:
            next_month = date(cursor.year + 1, 1, 1)
        else:
            next_month = date(cursor.year, cursor.month + 1, 1)
        month_end = next_month - timedelta(days=1)
        periods.append({
            "index": index,
            "label": f"{MONTHS_FR[cursor.month - 1]} {cursor.year}",
            "start": max(cursor, year.start_date),
            "end": min(month_end, year.end_date),
        })
        cursor = next_month
        index += 1
    return periods


@login_required
def permanent_annual_statement(request):
    year = viewed_year()
    periods = _school_year_periods(year)

    teacher_rows = []
    other_rows = []
    if year:
        teachers = Teacher.objects.filter(is_active=True, contract_type=Teacher.ContractType.PERMANENT).select_related("user").order_by("last_name", "first_name")
        others = OtherPersonnel.objects.filter(is_active=True, school=year.school, contract_type=OtherPersonnel.ContractType.PERMANENT).order_by("last_name", "first_name")

        paid_teacher = {(p.teacher_id, p.period): p for p in TeacherPayment.objects.filter(school_year=year, teacher__in=teachers)}
        paid_other = {(p.personnel_id, p.period): p for p in OtherPersonnelPayment.objects.filter(school_year=year, personnel__in=others)}

        if request.method == "POST":
            created, skipped, errors = 0, 0, []
            for t in teachers:
                for period in periods:
                    field = f"amount_teacher_{t.id}_{period['index']}"
                    raw = request.POST.get(field, "").strip()
                    if not raw or (t.id, period["label"]) in paid_teacher:
                        continue
                    try:
                        amount = Decimal(raw.replace(",", "."))
                    except Exception:
                        errors.append(f"{t.full_name} — {period['label']} : montant invalide.")
                        continue
                    try:
                        TeacherPayment(teacher=t, school_year=year, period=period["label"], amount=amount).save()
                        created += 1
                    except ValidationError as exc:
                        errors.append(f"{t.full_name} — {period['label']} : {'; '.join(exc.messages)}")
                    except Exception:
                        skipped += 1
            for p in others:
                for period in periods:
                    field = f"amount_other_{p.id}_{period['index']}"
                    raw = request.POST.get(field, "").strip()
                    if not raw or (p.id, period["label"]) in paid_other:
                        continue
                    try:
                        amount = Decimal(raw.replace(",", "."))
                    except Exception:
                        errors.append(f"{p.first_name} {p.last_name} — {period['label']} : montant invalide.")
                        continue
                    try:
                        OtherPersonnelPayment(personnel=p, school_year=year, period=period["label"], amount=amount).save()
                        created += 1
                    except ValidationError as exc:
                        errors.append(f"{p.first_name} {p.last_name} — {period['label']} : {'; '.join(exc.messages)}")
                    except Exception:
                        skipped += 1
            if created:
                messages.success(request, f"{created} salaire(s) enregistré(s).")
            for error in errors:
                messages.error(request, error)
            return redirect("permanent_annual_statement")

        for t in teachers:
            cells = []
            for period in periods:
                existing = paid_teacher.get((t.id, period["label"]))
                cells.append({"period": period, "existing": existing, "default": existing.amount if existing else t.monthly_salary})
            teacher_rows.append({"person": t, "label": t.full_name, "kind": "teacher", "cells": cells})

        for p in others:
            cells = []
            for period in periods:
                existing = paid_other.get((p.id, period["label"]))
                cells.append({"period": period, "existing": existing, "default": existing.amount if existing else p.monthly_salary})
            other_rows.append({"person": p, "label": f"{p.first_name} {p.last_name}", "kind": "other", "cells": cells})

    return render(request, "administration/salaries/annual_statement.html", {
        "school_year": year,
        "periods": periods,
        "teacher_rows": teacher_rows,
        "other_rows": other_rows,
    })


def _worked_hours(records):
    """Heures travaillées à partir de pointages (entrée/sortie), en Decimal."""
    total = Decimal("0")
    for r in records:
        if r.status in ("PRESENT", "LATE") and r.entry_time and r.exit_time:
            seconds = (
                r.exit_time.hour * 3600 + r.exit_time.minute * 60 + r.exit_time.second
                - (r.entry_time.hour * 3600 + r.entry_time.minute * 60 + r.entry_time.second)
            )
            if seconds > 0:
                total += Decimal(seconds) / Decimal(3600)
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@login_required
def hourly_monthly_statement(request):
    year = viewed_year()
    periods = _school_year_periods(year)

    try:
        selected_index = int(request.POST.get("period_index") or request.GET.get("period_index") or "")
    except (TypeError, ValueError):
        selected_index = None
    today = date.today()
    selected_period = next((p for p in periods if p["index"] == selected_index), None)
    if selected_period is None:
        selected_period = next((p for p in periods if p["start"] <= today <= p["end"]), periods[0] if periods else None)

    rows = []
    if year and selected_period:
        teachers = Teacher.objects.filter(is_active=True, hourly_rate__isnull=False).select_related("user").order_by("last_name", "first_name")
        others = OtherPersonnel.objects.filter(is_active=True, school=year.school, hourly_rate__isnull=False).order_by("last_name", "first_name")

        paid_teacher = {(p.teacher_id, p.period) for p in TeacherPayment.objects.filter(school_year=year, period=selected_period["label"])}
        paid_other = {(p.personnel_id, p.period) for p in OtherPersonnelPayment.objects.filter(school_year=year, period=selected_period["label"])}

        if request.method == "POST":
            created, errors = 0, []
            for t in teachers:
                if (t.id, selected_period["label"]) in paid_teacher:
                    continue
                raw = request.POST.get(f"amount_teacher_{t.id}", "").strip()
                if not raw:
                    continue
                try:
                    amount = Decimal(raw.replace(",", "."))
                    TeacherPayment(teacher=t, school_year=year, period=selected_period["label"], amount=amount).save()
                    created += 1
                except ValidationError as exc:
                    errors.append(f"{t.full_name} : {'; '.join(exc.messages)}")
                except Exception:
                    errors.append(f"{t.full_name} : montant invalide.")
            for p in others:
                if (p.id, selected_period["label"]) in paid_other:
                    continue
                raw = request.POST.get(f"amount_other_{p.id}", "").strip()
                if not raw:
                    continue
                try:
                    amount = Decimal(raw.replace(",", "."))
                    OtherPersonnelPayment(personnel=p, school_year=year, period=selected_period["label"], amount=amount).save()
                    created += 1
                except ValidationError as exc:
                    errors.append(f"{p.first_name} {p.last_name} : {'; '.join(exc.messages)}")
                except Exception:
                    errors.append(f"{p.first_name} {p.last_name} : montant invalide.")
            if created:
                messages.success(request, f"{created} salaire(s) horaire(s) enregistré(s).")
            for error in errors:
                messages.error(request, error)
            return redirect(f"{request.path}?period_index={selected_period['index']}")

        for t in teachers:
            records = TeacherAttendance.objects.filter(teacher=t, school_year=year, date__range=(selected_period["start"], selected_period["end"]))
            hours = _worked_hours(records)
            suggested = (hours * t.hourly_rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP) if t.hourly_rate else None
            already_paid = (t.id, selected_period["label"]) in paid_teacher
            rows.append({"label": t.full_name, "kind": "teacher", "id": t.id, "hours": hours, "hourly_rate": t.hourly_rate, "suggested": suggested, "paid": already_paid})

        for p in others:
            records = OtherPersonnelAttendance.objects.filter(personnel=p, school_year=year, date__range=(selected_period["start"], selected_period["end"]))
            hours = _worked_hours(records)
            suggested = (hours * p.hourly_rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP) if p.hourly_rate else None
            already_paid = (p.id, selected_period["label"]) in paid_other
            rows.append({"label": f"{p.first_name} {p.last_name}", "kind": "other", "id": p.id, "hours": hours, "hourly_rate": p.hourly_rate, "suggested": suggested, "paid": already_paid})

    return render(request, "administration/salaries/hourly_statement.html", {
        "school_year": year,
        "periods": periods,
        "selected_period": selected_period,
        "rows": rows,
    })
