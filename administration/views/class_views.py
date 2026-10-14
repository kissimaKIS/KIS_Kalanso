from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from administration.models import School, SchoolYear
from pedagogie.models import Classe, Enrollment
from administration.forms import ClasseForm
from common.utils import get_exam_info
from pedagogie.selectors.classes import ordered_classes
from common.years import viewed_year


@login_required
def classe_list(request):
    school = School.objects.filter(is_active=True).first()
    year = viewed_year() if school else None
    classes = (
        ordered_classes(
            Classe.objects.filter(school=school, school_year=year)
            .select_related("education_level")
            .prefetch_related("enrollments")
        )
        if year else Classe.objects.none()
    )
    return render(request, "administration/classes/list.html", {"classes": classes, "school_year": year})


@login_required
def add_classe(request):
    school = School.objects.filter(is_active=True).first()
    year = viewed_year() if school else None
    if not year or not school:
        return redirect("startup")
    form = ClasseForm(request.POST or None, school=school, school_year=year)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        # Déjà affectés dans le formulaire pour la validation du modèle ;
        # on les réaffirme ici avant l'enregistrement.
        obj.school, obj.school_year = school, year
        obj.save()
        return redirect("classe_detail", classe_id=obj.id)
    return render(request, "administration/classes/add_classe.html", {"form": form, "school_year": year})


@login_required
def classe_detail(request, classe_id):
    school = School.objects.filter(is_active=True).first()
    year = viewed_year() if school else None
    classe = get_object_or_404(Classe.objects.select_related("education_level"), id=classe_id, school=school, school_year=year)
    students = Enrollment.objects.filter(classe=classe).select_related("student")
    program_links = classe.programme_subject_links().order_by("order", "subject__name")
    return render(request, "administration/classes/classe_detail.html", {
        "classe": classe,
        "students": students,
        "exam_info": get_exam_info(classe),
        "program_links": program_links,
        "program_validated": classe.programme_valide,
    })


@login_required
def classe_modal(request):
    """Crée une classe depuis un parcours métier sans quitter la page."""
    from django.http import HttpResponse
    school = School.objects.filter(is_active=True).first()
    year = viewed_year() if school else None
    if not school or not year:
        return HttpResponse("<div class='kis-alert kis-alert-danger'>Aucune année scolaire active.</div>", status=400)

    form = ClasseForm(request.POST or None, school=school, school_year=year)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        response = HttpResponse(
            f'<option value="{obj.id}" selected>{obj.display_name}</option>'
        )
        response["HX-Trigger"] = "kisClassCreated"
        response["X-KIS-Class-Id"] = str(obj.id)
        response["X-KIS-Class-Label"] = str(obj)
        if request.GET.get("list") == "1":
            response = HttpResponse("", headers={"HX-Trigger": "kisModalReload"})
        return response

    return render(request, "administration/classes/_modal_form.html", {"form": form, "school_year": year, "list_mode": request.GET.get("list") == "1"})
