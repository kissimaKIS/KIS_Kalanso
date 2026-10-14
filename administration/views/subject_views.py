from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.http import HttpResponse
from django.utils.http import url_has_allowed_host_and_scheme
from django.db.models import Q
from administration.forms import SubjectForm
from administration.models import School, SchoolYear
from pedagogie.models import Subject, EducationLevelSubject


@login_required
def subject_list(request):
    school = School.objects.filter(is_active=True).first()
    enabled_types = school.enabled_school_types() if school else []
    subjects = Subject.objects.filter(is_active=True)
    if enabled_types:
        subjects = subjects.filter(
            Q(
                level_links__education_level__school_type__in=enabled_types,
                level_links__is_active=True,
                level_links__education_level__is_active=True,
            )
            | Q(
                track_level_links__track_level__track__school_type__in=enabled_types,
                track_level_links__is_active=True,
                track_level_links__track_level__is_active=True,
                track_level_links__track_level__track__is_active=True,
            )
        ).distinct()
    return render(request, "administration/subjects/list.html", {
        "subjects": subjects,
        "school": school,
        "enabled_types": enabled_types,
    })


def _is_modal_request(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _modal_reload_response():
    return HttpResponse("", headers={"HX-Trigger": "kisModalReload"})


def _safe_next_url(request, value):
    # Accept internal absolute-path URLs used by contextual modal workflows,
    # while rejecting protocol-relative/external destinations.
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    if value and url_has_allowed_host_and_scheme(
        value, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return value
    return ""


@login_required
def subject_create(request):
    next_url = _safe_next_url(request, request.POST.get("next") or request.GET.get("next"))
    form = SubjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        if _is_modal_request(request):
            return _modal_reload_response()
        return redirect(next_url or "subject_list")
    if _is_modal_request(request):
        return render(request, "administration/subjects/_modal_form.html", {
            "form": form, "submit_label": "Créer la matière", "next_url": next_url,
            "action_url": request.path,
        })
    return render(request, "administration/subjects/form.html", {
        "form": form,
        "title": "Nouvelle matière",
        "next_url": next_url,
    })
