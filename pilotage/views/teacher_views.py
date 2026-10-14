from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from administration.models import SchoolYear, Teacher
from ..models import TeacherEvaluation
from ..forms import TeacherEvaluationForm
from common.years import viewed_year
@login_required
def teacher_followup(request):
    year=viewed_year()
    teachers=Teacher.objects.filter(is_active=True).select_related("user").prefetch_related("evaluations")
    return render(request,"pilotage/teachers/list.html",{"teachers":teachers,"school_year":year})
@login_required
def teacher_evaluate(request, teacher_id):
    teacher=get_object_or_404(Teacher,pk=teacher_id); year=viewed_year(); form=TeacherEvaluationForm(request.POST or None)
    if request.method=="POST" and form.is_valid() and year:
        obj=form.save(commit=False); obj.teacher=teacher; obj.school_year=year; obj.save(); messages.success(request,"Suivi enseignant enregistré."); return redirect("teacher_followup")
    return render(request,"pilotage/teachers/form.html",{"form":form,"teacher":teacher})
