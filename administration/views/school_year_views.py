from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.db import transaction
from django.db.models import Count, Q
from django.contrib import messages

from administration.forms import SchoolYearForm
from administration.models import School, SchoolYear


def _current_school():
    """Return the active school used by the current single-school MVP context."""
    return School.objects.filter(is_active=True).order_by("id").first()


@login_required
def school_year_create(request):
    school = _current_school()
    if not school:
        return redirect("school_create")

    blocker = SchoolYear.creation_blocker(school.pk)
    if blocker:
        messages.info(request, blocker)
        return redirect("school_year_list")

    form = SchoolYearForm(request.POST or None, school=school)
    if request.method == "POST" and form.is_valid():
        school_year = form.save(commit=False)
        # SchoolYear.school is mandatory. Set it before the INSERT.
        school_year.school = school
        school_year.is_active = True
        school_year.save()

        # The year is created from the central catalogue. Let the administrator
        # immediately choose which levels/tracks are actually open this year.
        return redirect("school_year_catalog", pk=school_year.pk)

    return render(
        request,
        "administration/school_year/form.html",
        {"form": form, "title": "Créer l'année scolaire", "school": school},
    )


@login_required
def school_year_list(request):
    school = _current_school()
    years = (
        SchoolYear.objects.filter(school=school)
        .annotate(open_level_count=Count("configured_levels", filter=Q(configured_levels__is_active=True)))
        if school else SchoolYear.objects.none()
    )
    return render(
        request,
        "administration/school_year/list.html",
        {"years": years, "school": school, "creation_blocker": SchoolYear.creation_blocker(school.pk) if school else None},
    )


@login_required
def school_year_activate(request, pk):
    school = _current_school()
    year = get_object_or_404(SchoolYear, pk=pk, school=school)
    if request.method == "POST" and not year.is_closed:
        with transaction.atomic():
            # Changer explicitement d'année active est autorisé depuis les
            # paramètres. On désactive d'abord l'année courante afin que
            # SchoolYear.clean() puisse valider la nouvelle année active.
            SchoolYear.objects.filter(
                school=school, is_active=True, is_closed=False
            ).exclude(pk=year.pk).update(is_active=False)
            year.is_active = True
            year.save()
        messages.success(request, f"L'année scolaire {year.name} est maintenant active.")
    return redirect("school_year_list")


@login_required
def school_year_close(request, pk):
    school = _current_school()
    year = get_object_or_404(SchoolYear, pk=pk, school=school)
    if request.method == "POST" and year.is_active and not year.is_closed:
        year.is_closed = True
        year.is_active = False
        year.save()
        messages.success(request, f"L'année scolaire {year.name} a été clôturée. Aucune nouvelle année n'a été créée automatiquement.")

    return redirect("school_year_list")
