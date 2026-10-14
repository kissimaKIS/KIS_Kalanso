from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from common.pagination import paginate
from common.years import viewed_year
from pedagogie.models import Classe, Student

from .forms import DocumentForm
from .models import STUDENT_PIECES, Document


def _is_modal_request(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _modal_reload_response():
    return HttpResponse("", headers={"HX-Trigger": "kisModalReload"})


def _safe_next(request, default):
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return default


@login_required
def document_list(request):
    """Bibliothèque : filtre par catégorie, puis par classe et élève pour la catégorie Élève (V8-1)."""
    year = viewed_year()
    documents = Document.objects.select_related("student", "classe", "uploaded_by")
    category = request.GET.get("categorie", "")
    classe_id = request.GET.get("classe", "")
    search = (request.GET.get("q") or "").strip()
    if category in dict(Document.CATEGORY_CHOICES):
        documents = documents.filter(category=category)
    classe = None
    if category == "STUDENT" and classe_id.isdigit():
        classe = Classe.objects.filter(pk=classe_id).first()
        if classe:
            # Documents rattachés à la classe, ou à un élève inscrit dans cette classe.
            documents = documents.filter(Q(classe=classe) | Q(student__enrollments__classe=classe)).distinct()
    if search:
        documents = documents.filter(Q(title__icontains=search) | Q(student__first_name__icontains=search)
                                     | Q(student__last_name__icontains=search) | Q(student__matricule__icontains=search))
    classes = (Classe.objects.filter(school_year=year).select_related("education_level", "pedagogical_track")
               .order_by("education_level__order", "group", "name") if year else Classe.objects.none())
    page_obj = paginate(request, documents)
    return render(request, "documents/list.html", {
        "documents": page_obj, "page_obj": page_obj, "categories": Document.CATEGORY_CHOICES,
        "category": category, "classes": classes, "classe": classe, "search": search,
    })


@login_required
def document_create(request):
    initial = {}
    student = Student.objects.filter(pk=request.GET.get("student") or 0).first()
    if student:
        enrollment = student.enrollments.select_related("classe").order_by("-school_year__start_date").first()
        initial = {"category": "STUDENT", "student": student.pk, "classe": enrollment.classe_id if enrollment else None}
    elif request.GET.get("categorie") in dict(Document.CATEGORY_CHOICES):
        initial = {"category": request.GET["categorie"]}
    form = DocumentForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.uploaded_by = request.user
        obj.save()
        messages.success(request, "Document enregistré.")
        if _is_modal_request(request):
            return _modal_reload_response()
        return redirect(_safe_next(request, "document_list"))
    context = {"form": form, "action_url": request.get_full_path(), "student_pieces": STUDENT_PIECES,
               "next": request.GET.get("next", "")}
    if _is_modal_request(request):
        return render(request, "documents/_modal_form.html", context)
    return render(request, "documents/form.html", context)


@login_required
def document_delete(request, pk):
    obj = get_object_or_404(Document, pk=pk)
    default = "document_list"
    if request.method == "POST":
        title = obj.title
        obj.delete()
        messages.success(request, f"Document « {title} » supprimé.")
        return redirect(_safe_next(request, default))
    return render(request, "documents/confirm_delete.html", {"object": obj, "next": request.GET.get("next", "")})


@login_required
def document_students(request, classe_id):
    from django.utils.html import escape
    students = Student.objects.filter(enrollments__classe_id=classe_id).distinct().order_by("last_name", "first_name")
    options = ['<option value="">Sélectionnez un élève</option>' if students else '<option value="">Aucun élève dans cette classe</option>']
    options += [f'<option value="{s.id}">{escape(s.last_name)} {escape(s.first_name)}</option>' for s in students]
    return HttpResponse("".join(options))
