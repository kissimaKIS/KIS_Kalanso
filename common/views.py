from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from pedagogie.models import Bulletin, Classe, Enrollment, Term
# Les moteurs PDF (ReportLab) sont importés à la demande : les charger au
# démarrage ajoutait ~0,5 s à chaque lancement de l'application.


def render_bulletin_pdf(*args, **kwargs):
    from pedagogie.bulletin_pdf import render_bulletin_pdf as render
    return render(*args, **kwargs)


def render_bulletins_pdf(*args, **kwargs):
    from pedagogie.bulletin_pdf import render_bulletins_pdf as render
    return render(*args, **kwargs)


def render_ponctuel_pdf(*args, **kwargs):
    from pedagogie.bulletin_ponctuel_pdf import render_ponctuel_pdf as render
    return render(*args, **kwargs)


def render_ponctuel_pdf_classe(*args, **kwargs):
    from pedagogie.bulletin_ponctuel_pdf import render_ponctuel_pdf_classe as render
    return render(*args, **kwargs)


def bulletins_for(enrollments, term):
    """Bulletins d'une liste d'inscriptions, créés en une seule fois si besoin."""
    existing = {
        b.enrollment_id: b
        for b in Bulletin.objects.filter(enrollment__in=enrollments, term=term)
    }
    missing = [Bulletin(enrollment=e, term=term) for e in enrollments if e.id not in existing]
    if missing:
        Bulletin.objects.bulk_create(missing, ignore_conflicts=True)
        existing = {
            b.enrollment_id: b
            for b in Bulletin.objects.filter(enrollment__in=enrollments, term=term)
        }
    by_id = {e.id: e for e in enrollments}
    bulletins = []
    for enrollment in enrollments:
        bulletin = existing[enrollment.id]
        bulletin.enrollment = by_id[enrollment.id]
        bulletins.append(bulletin)
    return bulletins


@login_required
def bulletin_pdf(request, enrollment_id, term_id):
    enrollment = get_object_or_404(Enrollment, id=enrollment_id)
    term = get_object_or_404(Term, id=term_id, school_year=enrollment.school_year)
    bulletin, _ = Bulletin.objects.get_or_create(enrollment=enrollment, term=term)
    is_duplicate = request.GET.get("duplicate") == "1"
    data = render_bulletin_pdf(bulletin, copies_per_page=1, is_duplicate=is_duplicate)
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="{("duplicata_" if is_duplicate else "bulletin_")}{enrollment.student.matricule or enrollment.student.id}.pdf"'
    )
    return response


@login_required
def class_bulletins_pdf(request, classe_id, term_id):
    """Imprime tous les bulletins de la classe, selon le mode choisi."""
    from pedagogie.models import Classe

    classe = get_object_or_404(Classe, pk=classe_id)
    term = get_object_or_404(Term, pk=term_id, school_year=classe.school_year)
    try:
        copies_per_page = int(request.GET.get("copies_per_page", "1"))
    except (TypeError, ValueError):
        copies_per_page = 1
    if copies_per_page not in (1, 2):
        return HttpResponse("Le mode d'impression doit être 1 ou 2 bulletins par page.", status=400)

    enrollments = list(
        Enrollment.objects.filter(classe=classe)
        .select_related(
            "student", "school_year__school", "classe__education_level",
            "classe__pedagogical_track", "classe__school_year",
        )
        .order_by("student__first_name", "student__last_name")
    )
    if not enrollments:
        return HttpResponse("Aucun élève inscrit dans cette classe.", status=404)

    bulletins = bulletins_for(enrollments, term)
    from pedagogie.services.class_results import ClassTermResults
    results = ClassTermResults(classe, term)
    for bulletin in bulletins:
        bulletin._class_results = results
    data = render_bulletins_pdf(bulletins, copies_per_page=copies_per_page)
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="bulletins_classe_{classe.id}_{term.id}_{copies_per_page}parpage.pdf"'
    )
    return response


@login_required
def bulletin_ponctuel_pdf(request, enrollment_id, term_id):
    """Récapitulatif non officiel des évaluations ponctuelles pour un élève."""
    enrollment = get_object_or_404(Enrollment, id=enrollment_id)
    term = get_object_or_404(Term, id=term_id, school_year=enrollment.school_year)
    data = render_ponctuel_pdf(enrollment, term)
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="suivi-ponctuel_{enrollment.student.matricule or enrollment.student.id}.pdf"'
    )
    return response


@login_required
def class_ponctuel_pdf(request, classe_id, term_id):
    """Récapitulatif non officiel des évaluations ponctuelles pour toute la classe."""
    classe = get_object_or_404(Classe, pk=classe_id)
    term = get_object_or_404(Term, pk=term_id, school_year=classe.school_year)
    enrollments = list(
        Enrollment.objects.filter(classe=classe)
        .select_related(
            "student", "school_year__school", "classe__education_level",
            "classe__pedagogical_track", "classe__school_year",
        )
        .order_by("student__first_name", "student__last_name")
    )
    if not enrollments:
        return HttpResponse("Aucun élève inscrit dans cette classe.", status=404)
    data = render_ponctuel_pdf_classe(enrollments, term)
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="suivi-ponctuel_classe_{classe.id}_{term.id}.pdf"'
    return response
