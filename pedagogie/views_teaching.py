from collections import OrderedDict
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse

from administration.models import School, SchoolYear, Teacher
from .forms import TeachingForm
from .models import EducationLevel, Teaching
from .permissions import TeacherScope
from common.years import viewed_year


def _current_school():
    return School.objects.filter(is_active=True).order_by("id").first()


def _active_school_year(school):
    return viewed_year() if school else None


def _class_weekly_hours(classe):
    return sum((link.weekly_hours for link in classe.applicable_subject_links()), 0)


@login_required
def teaching_list(request):
    school = _current_school()
    year = _active_school_year(school)
    teachings = Teaching.objects.none()
    if school and year:
        teachings = Teaching.objects.filter(
            classe__school=school, classe__school_year=year
        ).select_related(
            "teacher__user", "subject", "classe", "classe__education_level", "classe__pedagogical_track"
        ).order_by("teacher__last_name", "teacher__first_name", "teacher_id", "classe__education_level__order", "classe__group")
        scope = TeacherScope(request.user)
        if not scope.unrestricted:
            # Un professeur ne consulte que ses propres affectations.
            teachings = teachings.filter(teacher=scope.teacher) if scope.teacher else Teaching.objects.none()

    status = request.GET.get("statut", "")
    profile = request.GET.get("profil", "")
    level_id = request.GET.get("niveau", "")
    search = request.GET.get("q", "").strip()
    if status:
        teachings = teachings.filter(teacher__contract_type=status)
    if profile:
        teachings = teachings.filter(teacher__pedagogical_profile=profile)
    if level_id:
        teachings = teachings.filter(classe__education_level_id=level_id)
    if search:
        teachings = teachings.filter(
            Q(teacher__employee_number__icontains=search)
            | Q(teacher__first_name__icontains=search)
            | Q(teacher__last_name__icontains=search)
        )

    # Programme de chaque classe chargé une seule fois (et non une requête
    # par affectation) : indispensable dès qu'il y a des centaines d'affectations.
    class_links = {}

    def links_for(classe):
        if classe.id not in class_links:
            links = list(classe.applicable_subject_links().filter(is_active=True))
            class_links[classe.id] = {
                "by_subject": {link.subject_id: link for link in links},
                "weekly_hours": sum((link.weekly_hours for link in links), 0),
            }
        return class_links[classe.id]

    grouped = OrderedDict()
    for teaching in teachings:
        teacher = teaching.teacher
        item = grouped.setdefault(teacher.pk, {
            "teacher": teacher,
            "assignments": [],
            "levels": [],
            "classes": [],
            "subjects": [],
            "charges": [],
        })
        classe_label = str(teaching.classe)
        level_label = teaching.classe.education_level.name
        programme = links_for(teaching.classe)
        if teaching.subject_id:
            contextual_link = programme["by_subject"].get(teaching.subject_id)
            subject_label = contextual_link.name if contextual_link else str(teaching.subject)
            hours = contextual_link.weekly_hours if contextual_link else 0
            charge_label = f"{hours:g} h/sem"
        else:
            subject_label = "—"
            hours = programme["weekly_hours"]
            charge_label = f"{hours:g} h/sem"
        item["assignments"].append({"id": teaching.pk, "class": classe_label, "subject": subject_label, "hours": charge_label})
        if level_label not in item["levels"]:
            item["levels"].append(level_label)
        if classe_label not in item["classes"]:
            item["classes"].append(classe_label)
        if subject_label != "—" and subject_label not in item["subjects"]:
            item["subjects"].append(subject_label)
        item["charges"].append(charge_label)

    profiles = []
    if school:
        allowed = set(school.enabled_school_types())
        if School.SchoolType.FUNDAMENTAL_1 in allowed:
            profiles.append(Teacher.PedagogicalProfile.GENERALISTE)
        if School.SchoolType.FUNDAMENTAL_2 in allowed or School.SchoolType.HIGH_SCHOOL in allowed:
            profiles.append(Teacher.PedagogicalProfile.SPECIALISTE)
        if School.SchoolType.VOCATIONAL in allowed:
            profiles.append(Teacher.PedagogicalProfile.FORMATEUR_METIER)
    profile_choices = [(p.value, p.label) for p in profiles]
    if profile not in {value for value, _ in profile_choices}:
        profile = ""
    levels = []
    if school and year:
        levels = list(
            EducationLevel.objects.filter(
                school_year_configurations__school_year=year,
                school_year_configurations__is_active=True,
                school_type__in=school.enabled_school_types(),
                is_active=True,
            ).distinct().order_by("order", "id")
        )
    if str(level_id) not in {str(level.pk) for level in levels}:
        level_id = ""

    return render(request, "pedagogie/teaching/list.html", {
        "groups": list(grouped.values()),
        "contract_types": Teacher.ContractType.choices,
        "profiles": profile_choices,
        "selected_status": status,
        "selected_profile": profile,
        "levels": levels,
        "selected_level": level_id,
        "search": search,
        "school_year": year,
    })


def _is_modal_request(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _modal_reload_response():
    return HttpResponse("", headers={"HX-Trigger": "kisModalReload"})


@login_required
def teaching_create(request):
    school = _current_school()
    year = _active_school_year(school)
    if not school or not year:
        return redirect("dashboard")
    form = TeachingForm(request.POST or None, school=school, school_year=year)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Affectation enregistrée.")
        if _is_modal_request(request):
            return _modal_reload_response()
        return redirect("teaching_list")
    teacher_profiles = {str(t.pk): t.pedagogical_profile for t in form.fields["teacher"].queryset}
    context = {
        "form": form,
        "school_year": year,
        "teacher_profiles": json.dumps(teacher_profiles),
        "class_subjects": json.dumps(form.class_subjects),
    }
    if _is_modal_request(request):
        context["action_url"] = request.path
        return render(request, "pedagogie/teaching/_modal_form.html", context)
    return render(request, "pedagogie/teaching/form.html", context)


@login_required
def teaching_delete(request, pk):
    obj = get_object_or_404(Teaching.objects.select_related("teacher__user", "classe"), pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Affectation supprimée.")
        return redirect("teaching_list")
    return render(request, "pedagogie/teaching/delete.html", {"object": obj})
