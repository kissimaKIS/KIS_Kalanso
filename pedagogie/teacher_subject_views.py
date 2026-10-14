from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from administration.models import Teacher
from .forms import TeacherSubjectForm
from .models import TeacherSubject

@login_required
def teacher_subjects(request, teacher_id):
    teacher = get_object_or_404(Teacher.objects.select_related("user"), pk=teacher_id)
    if request.method == "POST":
        form = TeacherSubjectForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.teacher = teacher
            obj.save()
            messages.success(request, "Matière ajoutée aux compétences de l'enseignant.")
            return redirect("teacher_subjects", teacher_id=teacher.id)
    else:
        form = TeacherSubjectForm()
    subjects = teacher.qualified_subjects.select_related("subject").order_by("subject__name")
    return render(request, "pedagogie/teacher_subjects.html", {
        "teacher": teacher, "form": form, "subjects": subjects,
    })

@login_required
def teacher_subject_delete(request, pk):
    obj = get_object_or_404(TeacherSubject.objects.select_related("teacher__user", "subject"), pk=pk)
    teacher_id = obj.teacher_id
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Compétence retirée.")
    return redirect("teacher_subjects", teacher_id=teacher_id)
