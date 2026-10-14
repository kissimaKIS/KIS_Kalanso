"""Pages « Saisie mobile » : envoi des paquets aux enseignants et chargement des notes."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from administration.models import SchoolYear, Teacher
from . import mobile_grades as mg
from .models import BulletinItem, BulletinLock, Classe, MobileGradeSubmission, Term


def _active_terms():
    year = SchoolYear.objects.filter(is_active=True, is_closed=False).first()
    return year, list(Term.objects.filter(school_year=year).order_by("order", "id")) if year else []


@login_required
def mobile_home(request):
    year, terms = _active_terms()
    term = None
    wanted = request.GET.get("term")
    if terms:
        term = next((t for t in terms if str(t.id) == wanted), terms[-1])
    teachers, classes = [], []
    if term:
        for teacher in mg.mobile_teachers(term):
            sheets, warnings = mg.teacher_sheets(teacher, term)
            teachers.append({"teacher": teacher, "sheets": sheets, "warnings": warnings})
        configured = set(BulletinItem.objects.filter(classe__school_year=term.school_year, is_active=True).values_list("classe_id", flat=True))
        locked = set(BulletinLock.objects.filter(term=term).values_list("classe_id", flat=True))
        for classe in mg.mobile_classes(term):
            classes.append({"classe": classe, "configured": classe.id in configured, "locked": classe.id in locked})
    return render(request, "pedagogie/mobile/home.html", {
        "year": year, "terms": terms, "term": term, "teachers": teachers, "classes": classes,
        "submissions": MobileGradeSubmission.objects.select_related("package__teacher", "package__term", "imported_by")[:30],
    })


@login_required
@require_POST
def mobile_package_download(request):
    term = get_object_or_404(Term, pk=request.POST.get("term"), school_year__is_active=True, school_year__is_closed=False)
    teacher, classes = None, None
    if request.POST.get("teacher"):
        teacher = get_object_or_404(Teacher, pk=request.POST.get("teacher"))
    else:
        ids = [int(x) for x in request.POST.getlist("classes") if x.isdigit()]
        classes = list(Classe.objects.filter(pk__in=ids, school_year=term.school_year).select_related("education_level"))
        if not classes:
            messages.error(request, "Cochez au moins une classe.")
            return redirect(f"{reverse('mobile_home')}?term={term.id}")
    try:
        package, _ = mg.build_package(teacher, term, request.user, classes=classes, label=(request.POST.get("label") or "").strip())
    except mg.MobileImportError as exc:
        messages.error(request, str(exc))
        return redirect(f"{reverse('mobile_home')}?term={term.id}")
    response = HttpResponse(mg.package_json(package), content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{mg.package_filename(package)}"'
    return response


@login_required
@require_POST
def mobile_submission_upload(request):
    upload = request.FILES.get("notes")
    if not upload:
        messages.error(request, "Choisissez le fichier de notes reçu de l'enseignant (.json).")
        return redirect("mobile_home")
    try:
        submission = mg.read_submission(upload.read(mg.MAX_FILE_SIZE + 1), upload.name, request.user)
    except mg.MobileImportError as exc:
        messages.error(request, str(exc))
        return redirect("mobile_home")
    return redirect("mobile_submission_detail", pk=submission.pk)


@login_required
def mobile_submission_detail(request, pk):
    submission = get_object_or_404(MobileGradeSubmission.objects.select_related("package__teacher", "package__term__school_year"), pk=pk)
    report = mg.analyse(submission) if submission.status == MobileGradeSubmission.Status.PENDING else None
    return render(request, "pedagogie/mobile/submission.html", {"submission": submission, "report": report})


@login_required
@require_POST
def mobile_submission_apply(request, pk):
    submission = get_object_or_404(MobileGradeSubmission, pk=pk)
    try:
        written = mg.apply(submission, request.user)
    except mg.MobileImportError as exc:
        messages.error(request, str(exc))
        return redirect("mobile_submission_detail", pk=pk)
    messages.success(request, f"{written} note(s) enregistrée(s) — {submission.package.holder}.")
    return redirect("mobile_home")


@login_required
@require_POST
def mobile_submission_cancel(request, pk):
    submission = get_object_or_404(MobileGradeSubmission, pk=pk, status=MobileGradeSubmission.Status.PENDING)
    submission.status = MobileGradeSubmission.Status.CANCELLED
    submission.save(update_fields=["status"])
    messages.info(request, "Dépôt abandonné : aucune note n'a été modifiée.")
    return redirect("mobile_home")
