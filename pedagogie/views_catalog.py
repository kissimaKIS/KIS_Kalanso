from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction, IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse
from django.utils.http import url_has_allowed_host_and_scheme

from administration.models import School, SchoolYear
from .forms_catalog import SchoolYearCatalogForm, EducationLevelSubjectForm, TrackLevelSubjectForm, PedagogicalTrackForm, PreschoolSubjectCopyForm
from .forms import SubjectForm
from .models import (EducationLevel, EducationLevelSubject, PedagogicalTrack, SchoolYearLevel, SchoolYearTrack,
                     Subject, TrackLevel, TrackLevelSubject)


SECTOR_ORDER = {code: index for index, (code, _label) in enumerate(School.SchoolType.choices, start=1)}


def _sector_groups(school_year):
    enabled = set(school_year.school.enabled_school_types())
    rows = []
    for code, label in School.SchoolType.choices:
        if code not in enabled:
            continue
        levels = list(
            SchoolYearLevel.objects.filter(
                school_year=school_year,
                education_level__school_type=code,
                is_active=True,
            ).select_related("education_level")
        )
        tracks = list(
            SchoolYearTrack.objects.filter(
                school_year=school_year,
                is_active=True,
                track__school_type=code,
                track__is_active=True,
            ).select_related("track").prefetch_related("track__levels")
        )
        domain_groups = []
        seen = {}
        for track in tracks:
            domain = (track.track.domain or "").strip() or "Autres formations"
            if domain not in seen:
                seen[domain] = {"domain": domain, "tracks": []}
                domain_groups.append(seen[domain])
            seen[domain]["tracks"].append(track)
        rows.append({"code": code, "label": label, "levels": levels, "tracks": tracks, "track_groups": domain_groups})
    return rows


def _invalidate_year_catalogs_for_level(level_id):
    for year in SchoolYear.objects.filter(configured_levels__education_level_id=level_id, configured_levels__is_active=True):
        year.invalidate_catalog()


def _invalidate_year_catalogs_for_track(track_id):
    for year in SchoolYear.objects.filter(configured_tracks__track_id=track_id, configured_tracks__is_active=True):
        year.invalidate_catalog()


@user_passes_test(lambda u: u.is_authenticated and u.has_admin_role())
def school_year_catalog(request, pk):
    school = School.objects.filter(is_active=True).first()
    school_year = get_object_or_404(SchoolYear.objects.select_related("school"), pk=pk)
    if not school or school_year.school_id != school.id:
        return redirect("school_year_list")
    if school_year.is_closed:
        messages.info(request, "Cette année scolaire est clôturée : sa configuration pédagogique est en lecture seule.")
        return redirect("school_year_list")

    form = SchoolYearCatalogForm(request.POST or None, school_year=school_year)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
            # La seule action de cette page est de vérifier puis valider la
            # configuration. La validation enregistre donc aussi les choix
            # affichés dans le formulaire : aucun bouton « Enregistrer les
            # modifications » séparé n'est nécessaire.
            school_year.validate_catalog(request.user)
        messages.success(request, "La configuration pédagogique a été vérifiée, enregistrée et validée par l'administrateur.")
        return redirect("school_year_catalog", pk=school_year.pk)

    return render(request, "pedagogie/catalog/school_year.html", {
        "school_year": school_year,
        "form": form,
        "sector_groups": _sector_groups(school_year),
        "levels_count": SchoolYearLevel.objects.filter(school_year=school_year, is_active=True).count(),
        "tracks_count": SchoolYearTrack.objects.filter(school_year=school_year, is_active=True).count(),
    })


@user_passes_test(lambda u: u.is_authenticated and u.has_admin_role())
def school_year_catalog_validate(request, pk):
    school = School.objects.filter(is_active=True).first()
    school_year = get_object_or_404(SchoolYear.objects.select_related("school"), pk=pk)
    if not school or school_year.school_id != school.id:
        return redirect("school_year_list")
    if request.method != "POST":
        return redirect("school_year_catalog", pk=school_year.pk)
    if school_year.is_closed:
        messages.error(request, "Cette année scolaire est clôturée : sa configuration ne peut plus être validée.")
        return redirect("school_year_catalog", pk=school_year.pk)

    active_levels = SchoolYearLevel.objects.filter(school_year=school_year, is_active=True)
    active_tracks = SchoolYearTrack.objects.filter(school_year=school_year, is_active=True)
    if not active_levels.exists():
        messages.error(request, "Impossible de valider : aucun niveau n'est ouvert pour cette année scolaire.")
        return redirect("school_year_catalog", pk=school_year.pk)

    school_year.validate_catalog(request.user)
    messages.success(request, "La configuration pédagogique a été vérifiée et validée par l'administrateur.")
    return redirect("school_year_catalog", pk=school_year.pk)

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


def _is_modal_request(request):
    # Support both AJAX requests and direct modal rendering (e.g. ?modal=1).
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.GET.get("modal") == "1"
        or request.POST.get("modal") == "1"
    )


def _modal_reload_response():
    return HttpResponse("", headers={"HX-Trigger": "kisModalReload"})


def _context_from_next(next_url):
    """Resolve a contextual destination used by the new-subject workflow."""
    parts = [part for part in (next_url or "").split("/") if part]
    try:
        if len(parts) >= 5 and parts[:3] == ["pedagogie", "referentiel", "niveaux"] and parts[4] == "matieres":
            return "level", int(parts[3])
        if len(parts) >= 5 and parts[:3] == ["pedagogie", "referentiel", "parcours"] and parts[4] == "matieres":
            return "track", int(parts[3])
    except (TypeError, ValueError):
        pass
    return None, None


@user_passes_test(lambda u: u.is_authenticated and u.has_admin_role())
def subject_add(request):
    next_url = _safe_next_url(request, request.POST.get("next") or request.GET.get("next"))
    if request.method == "POST":
        form = SubjectForm(request.POST)
        if form.is_valid():
            # Cette page crée uniquement la référence pédagogique.
            # L'association à un niveau/parcours et son nom affiché restent
            # des données contextuelles, gérées par « Ajouter existante ».
            subject = form.save()
            messages.success(request, f"{subject.name} a été créée.")
            if _is_modal_request(request):
                return _modal_reload_response()
            return redirect(next_url or "school_year_list")
    else:
        form = SubjectForm()
    if _is_modal_request(request):
        return render(request, "pedagogie/catalog/_modal_form.html", {
            "form": form, "submit_label": "Créer la matière", "next_url": next_url,
            "action_url": request.path,
        })
    return render(request, "pedagogie/catalog/subject_form.html", {
        "title": "Nouvelle matière", "context_label": "Référentiel pédagogique",
        "form": form, "next_url": next_url,
        "school": School.objects.filter(is_active=True).first(),
    })


@user_passes_test(lambda u: u.is_authenticated and u.has_admin_role())
def subject_edit(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    next_url = _safe_next_url(request, request.POST.get("next") or request.GET.get("next"))
    if request.method == "POST":
        form = SubjectForm(request.POST, instance=subject)
        if form.is_valid():
            form.save()
            messages.success(request, "La matière a été mise à jour.")
            if _is_modal_request(request):
                return _modal_reload_response()
            return redirect(next_url or "school_year_list")
    else:
        form = SubjectForm(instance=subject)
    if _is_modal_request(request):
        return render(request, "pedagogie/catalog/_modal_form.html", {
            "form": form, "submit_label": "Enregistrer", "next_url": next_url,
            "action_url": request.path,
        })
    return render(request, "pedagogie/catalog/subject_form.html", {
        "title": f"Modifier la matière — {subject.name}",
        "context_label": "Référentiel pédagogique",
        "form": form,
        "next_url": next_url,
        "school": School.objects.filter(is_active=True).first(),
    })

@user_passes_test(lambda u: u.is_authenticated and u.has_admin_role())
def level_subjects(request, pk):
    level = get_object_or_404(EducationLevel, pk=pk, is_active=True)
    school = School.objects.filter(is_active=True).first()
    if not school or level.school_type not in school.enabled_school_types():
        return redirect("school_year_list")
    # Lycée et centre professionnel sont organisés par séries/filières/
    # spécialités réelles ; leurs niveaux génériques ne sont jamais éditables.
    if level.school_type in {School.SchoolType.HIGH_SCHOOL, School.SchoolType.VOCATIONAL}:
        current_year = SchoolYear.objects.filter(school=school, is_active=True, is_closed=False).first()
        return redirect("school_year_catalog", pk=current_year.pk) if current_year else redirect("school_year_list")

    if request.method == "POST":
        form = EducationLevelSubjectForm(request.POST, education_level=level)
        if form.is_valid():
            link = form.save(commit=False)
            link.education_level = level
            try:
                with transaction.atomic():
                    link.save()
            except IntegrityError:
                form.add_error("name", "Cette matière est déjà associée à ce niveau.")
            else:
                _invalidate_year_catalogs_for_level(level.id)
                messages.success(request, f"{link.name} a été ajoutée au niveau {level.name}.")
                if _is_modal_request(request):
                    return _modal_reload_response()
                return redirect("level_subjects", pk=level.pk)
    else:
        form = EducationLevelSubjectForm(education_level=level)

    if _is_modal_request(request):
        return render(request, "pedagogie/catalog/_modal_form.html", {
            "form": form, "submit_label": "Ajouter au niveau",
            "action_url": request.path,
            "next_url": _safe_next_url(request, request.POST.get("next") or request.GET.get("next")),
        })

    links = EducationLevelSubject.objects.filter(education_level=level).select_related("subject").order_by("order", "subject__name")
    school_year = SchoolYear.objects.filter(school=school, is_active=True, is_closed=False).order_by("id").first()
    return render(request, "pedagogie/catalog/level_subjects.html", {
        "level": level, "links": links, "form": form, "school": school, "school_year": school_year,
    })


@user_passes_test(lambda u: u.is_authenticated and u.has_admin_role())
def preschool_subjects_copy(request, pk):
    target = get_object_or_404(EducationLevel, pk=pk, is_active=True)
    school = School.objects.filter(is_active=True).first()
    if not school or target.school_type != School.SchoolType.PRESCHOOL or target.school_type not in school.enabled_school_types():
        return redirect("school_year_list")
    form = PreschoolSubjectCopyForm(request.POST or None, target_level=target)
    if request.method == "POST" and form.is_valid():
        source = form.cleaned_data["source_level"]
        source_links = list(EducationLevelSubject.objects.filter(
            education_level=source, is_active=True
        ).select_related("subject").order_by("order", "id"))
        existing_subject_ids = set(EducationLevelSubject.objects.filter(
            education_level=target
        ).values_list("subject_id", flat=True))
        next_order = EducationLevelSubject.objects.filter(education_level=target).order_by("-order").values_list("order", flat=True).first() or 0
        copied = 0
        for source_link in source_links:
            if source_link.subject_id in existing_subject_ids:
                continue
            next_order += 1
            EducationLevelSubject.objects.create(
                education_level=target,
                subject=source_link.subject,
                name=source_link.name or source_link.subject.name,
                coefficient=source_link.coefficient,
                weekly_hours=source_link.weekly_hours,
                weekly_hours_max=source_link.weekly_hours_max,
                role=source_link.role,
                is_required=source_link.is_required,
                order=next_order,
                is_active=True,
            )
            existing_subject_ids.add(source_link.subject_id)
            copied += 1
        _invalidate_year_catalogs_for_level(target.id)
        if copied:
            messages.success(request, f"{copied} matière(s) copiée(s) depuis {source.name} vers {target.name}.")
        else:
            messages.info(request, "Aucune nouvelle matière à copier : les matières du niveau source sont déjà présentes.")
        if _is_modal_request(request):
            return _modal_reload_response()
        return redirect("level_subjects", pk=target.pk)
    if _is_modal_request(request):
        return render(request, "pedagogie/catalog/_copy_preschool_subjects.html", {
            "form": form, "target_level": target, "action_url": request.path,
        })
    return render(request, "pedagogie/catalog/copy_preschool_subjects.html", {
        "form": form, "target_level": target,
    })


@user_passes_test(lambda u: u.is_authenticated and u.has_admin_role())
def level_subject_edit(request, pk):
    link = get_object_or_404(EducationLevelSubject.objects.select_related("education_level", "subject"), pk=pk)
    school = School.objects.filter(is_active=True).first()
    if not school or link.education_level.school_type not in school.enabled_school_types():
        return redirect("school_year_list")
    next_url = _safe_next_url(request, request.POST.get("next") or request.GET.get("next"))
    if request.method == "POST":
        form = EducationLevelSubjectForm(request.POST, instance=link, education_level=link.education_level)
        if form.is_valid():
            form.save()
            _invalidate_year_catalogs_for_level(link.education_level_id)
            messages.success(request, f"La configuration de {link.name} a été mise à jour.")
            if _is_modal_request(request):
                return _modal_reload_response()
            return redirect(next_url or "level_subjects", pk=link.education_level_id)
    else:
        form = EducationLevelSubjectForm(instance=link, education_level=link.education_level)
    if _is_modal_request(request):
        return render(request, "pedagogie/catalog/_modal_form.html", {
            "form": form, "submit_label": "Enregistrer",
            "action_url": request.path, "next_url": next_url,
        })
    return render(request, "pedagogie/catalog/subject_form.html", {
        "title": f"Modifier — {link.name}",
        "context_label": link.education_level.name,
        "form": form,
        "back_url": "level_subjects",
        "back_pk": link.education_level_id,
        "next_url": next_url,
        "school": school,
    })


@user_passes_test(lambda u: u.is_authenticated and u.has_admin_role())
def level_subject_toggle(request, pk):
    link = get_object_or_404(EducationLevelSubject.objects.select_related("education_level", "subject"), pk=pk)
    if request.method != "POST":
        return redirect("level_subjects", pk=link.education_level_id)
    school = School.objects.filter(is_active=True).first()
    if school and link.education_level.school_type in school.enabled_school_types():
        link.is_active = not link.is_active
        link.save(update_fields=["is_active"])
        _invalidate_year_catalogs_for_level(link.education_level_id)
        messages.success(request, f"{link.name} est maintenant {'active' if link.is_active else 'inactive'} pour {link.education_level.name}.")
    return redirect("level_subjects", pk=link.education_level_id)


@user_passes_test(lambda u: u.is_authenticated and u.has_admin_role())
def track_edit(request, pk):
    track = get_object_or_404(PedagogicalTrack, pk=pk)
    school = School.objects.filter(is_active=True).first()
    if not school or track.school_type not in school.enabled_school_types():
        return redirect("school_year_list")
    next_url = _safe_next_url(request, request.POST.get("next") or request.GET.get("next"))
    if request.method == "POST":
        form = PedagogicalTrackForm(request.POST, instance=track)
        if form.is_valid():
            form.save()
            _invalidate_year_catalogs_for_track(track.id)
            messages.success(request, f"{track.name} a été mis à jour dans le référentiel.")
            if _is_modal_request(request):
                return _modal_reload_response()
            return redirect(next_url or "school_year_catalog", pk=SchoolYear.objects.filter(school=school, is_active=True, is_closed=False).values_list("pk", flat=True).first())
    else:
        form = PedagogicalTrackForm(instance=track)
    if _is_modal_request(request):
        return render(request, "pedagogie/catalog/_modal_form.html", {"form": form, "submit_label": "Enregistrer", "action_url": request.path, "next_url": next_url})
    return render(request, "pedagogie/catalog/track_form.html", {"form": form, "track": track, "school": school, "next_url": next_url})


@user_passes_test(lambda u: u.is_authenticated and u.has_admin_role())
def track_subjects(request, pk):
    track_level = get_object_or_404(TrackLevel.objects.select_related("track", "education_level"), pk=pk, is_active=True)
    school = School.objects.filter(is_active=True).first()
    if not school or track_level.track.school_type not in school.enabled_school_types():
        return redirect("school_year_list")
    if request.method == "POST":
        form = TrackLevelSubjectForm(request.POST, track_level=track_level)
        if form.is_valid():
            link = form.save(commit=False)
            link.track_level = track_level
            link.save()
            _invalidate_year_catalogs_for_track(track_level.track_id)
            messages.success(request, f"{link.name} a été ajoutée à {track_level.track.name} — {track_level.education_level.name}.")
            if _is_modal_request(request):
                return _modal_reload_response()
            return redirect("track_subjects", pk=track_level.pk)
    else:
        form = TrackLevelSubjectForm(track_level=track_level)
    if request.method == "POST" and _is_modal_request(request):
        return render(request, "pedagogie/catalog/_modal_form.html", {
            "form": form, "submit_label": "Ajouter au parcours",
            "action_url": request.path,
        })
    links = TrackLevelSubject.objects.filter(track_level=track_level).select_related("subject").order_by("order", "subject__name")
    school_year = SchoolYear.objects.filter(
        school=school, is_active=True, is_closed=False,
        configured_tracks__track=track_level.track, configured_tracks__is_active=True,
    ).order_by("id").first()
    return render(request, "pedagogie/catalog/track_subjects.html", {
        "track_level": track_level, "links": links, "form": form, "school": school, "school_year": school_year,
    })


@user_passes_test(lambda u: u.is_authenticated and u.has_admin_role())
def track_subject_edit(request, pk):
    link = get_object_or_404(TrackLevelSubject.objects.select_related("track_level__track", "track_level__education_level", "subject"), pk=pk)
    school = School.objects.filter(is_active=True).first()
    if not school or link.track_level.track.school_type not in school.enabled_school_types():
        return redirect("school_year_list")
    next_url = _safe_next_url(request, request.POST.get("next") or request.GET.get("next"))
    if request.method == "POST":
        form = TrackLevelSubjectForm(request.POST, instance=link, track_level=link.track_level)
        if form.is_valid():
            form.save()
            _invalidate_year_catalogs_for_track(link.track_level.track_id)
            messages.success(request, f"La configuration de {link.name} a été mise à jour.")
            if _is_modal_request(request):
                return _modal_reload_response()
            return redirect(next_url or "track_subjects", pk=link.track_level_id)
    else:
        form = TrackLevelSubjectForm(instance=link, track_level=link.track_level)
    if _is_modal_request(request):
        return render(request, "pedagogie/catalog/_modal_form.html", {
            "form": form, "submit_label": "Enregistrer",
            "action_url": request.path, "next_url": next_url,
        })
    return render(request, "pedagogie/catalog/subject_form.html", {
        "title": f"Modifier — {link.name}",
        "context_label": f"{link.track_level.track.name} — {link.track_level.education_level.name}",
        "form": form,
        "back_url": "track_subjects",
        "back_pk": link.track_level_id,
        "next_url": next_url,
        "school": school,
    })


@user_passes_test(lambda u: u.is_authenticated and u.has_admin_role())
def track_subject_toggle(request, pk):
    link = get_object_or_404(TrackLevelSubject.objects.select_related("track_level__track"), pk=pk)
    if request.method != "POST":
        return redirect("track_subjects", pk=link.track_level_id)
    school = School.objects.filter(is_active=True).first()
    if school and link.track_level.track.school_type in school.enabled_school_types():
        link.is_active = not link.is_active
        link.save(update_fields=["is_active"])
        _invalidate_year_catalogs_for_track(link.track_level.track_id)
        messages.success(request, f"La matière est maintenant {'active' if link.is_active else 'inactive'} pour ce parcours.")
    return redirect("track_subjects", pk=link.track_level_id)
