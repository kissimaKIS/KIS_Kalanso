from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from administration.forms import SchoolForm
from administration.models import School
from administration.services.configuration import school_configuration_checklist


@login_required
def school_create(request):
    school = School.objects.filter(is_active=True).first()
    if school:
        return redirect("school_edit", pk=school.pk)
    form = SchoolForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("startup")
    return render(request, "administration/school/form.html", {"form": form, "title": "Configurer l'établissement"})


@login_required
def school_edit(request, pk):
    school = get_object_or_404(School, pk=pk)
    form = SchoolForm(request.POST or None, request.FILES or None, instance=school)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Les informations de l’établissement ont été mises à jour.")
        return redirect("school_edit", pk=school.pk)
    return render(request, "administration/school/form.html", {"form": form, "school": school, "title": "Établissement", "configuration": school_configuration_checklist(school)})
