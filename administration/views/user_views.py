from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse

from administration.forms.user_form import UserCreateForm, UserUpdateForm
from administration.permissions.access import user_permissions
from administration.permissions.middleware import deny


def _can_manage(request_user, target):
    """Interdit de modifier un compte disposant de plus de droits que soi."""
    return user_permissions(target) <= user_permissions(request_user)


@login_required
def user_list(request):
    users = list(get_user_model().objects.prefetch_related("role_assignments").select_related("teacher_profile").order_by("last_name", "first_name", "username"))
    for user in users:
        user.kis_can_manage = _can_manage(request.user, user)
    return render(request, "administration/users/list.html", {"users": users})


def _is_modal_request(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _modal_reload_response():
    return HttpResponse("", headers={"HX-Trigger": "kisModalReload"})


@login_required
def user_create(request):
    form = UserCreateForm(request.POST or None, request_user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Utilisateur créé.")
        if _is_modal_request(request):
            return _modal_reload_response()
        return redirect("user_list")
    if _is_modal_request(request):
        return render(request, "administration/users/_modal_form.html", {"form": form, "action_url": request.path})
    return render(request, "administration/users/form.html", {"form": form, "page_title": "Nouvel utilisateur"})


@login_required
def user_edit(request, pk):
    obj = get_object_or_404(get_user_model(), pk=pk)
    if not _can_manage(request.user, obj):
        return deny(request, "Ce compte dispose de droits supérieurs aux vôtres.")
    form = UserUpdateForm(request.POST or None, instance=obj, request_user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Utilisateur mis à jour.")
        if _is_modal_request(request):
            return _modal_reload_response()
        return redirect("user_list")
    if _is_modal_request(request):
        return render(request, "administration/users/_modal_form.html", {"form": form, "action_url": request.path})
    return render(request, "administration/users/form.html", {"form": form, "page_title": "Modifier l'utilisateur"})


@login_required
def user_toggle(request, pk):
    obj = get_object_or_404(get_user_model(), pk=pk)
    if not _can_manage(request.user, obj):
        return deny(request, "Ce compte dispose de droits supérieurs aux vôtres.")
    if request.method == "POST" and obj != request.user:
        obj.is_active = not obj.is_active
        obj.save(update_fields=["is_active"])
        messages.success(request, "Statut utilisateur mis à jour.")
    return redirect("user_list")
