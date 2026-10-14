from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from administration.models import School
from .central_license import load_central_license, request_activation, school_edition, machine_id
from .license import current_license_label, license_status


def _school():
    return School.objects.filter(is_active=True).first()


def _activation_payload(school):
    try:
        return request_activation(school)
    except ValueError as exc:
        # L'écran de licence doit rester accessible même si l'édition
        # commerciale n'a pas encore été paramétrée dans l'établissement.
        return {"status": "error", "message": str(exc)}


@login_required
def license_activation(request):
    school = _school()
    result = None
    if school and license_status() != "commercial":
        result = _activation_payload(school)
        if result.get("status") == "success":
            messages.success(request, "Licence KIS Kalanso activée automatiquement.")
            return redirect("startup")
        if result.get("status") == "error" and request.method == "POST":
            messages.error(request, result.get("message", "Activation impossible."))
    elif not school and request.method == "POST":
        messages.error(request, "Aucun établissement configuré.")
    central = load_central_license()
    edition = None
    if school:
        try:
            _, edition = school_edition(school)
        except ValueError:
            edition = None
    return render(request, "common/license_activation.html", {
        "machine_id": machine_id(),
        "license_status": license_status(),
        "license_label": current_license_label(),
        "commercial_license": central,
        "school": school,
        "edition": edition,
        "activation_result": result,
    })


@login_required
@require_POST
def license_check(request):
    school = _school()
    if not school:
        return JsonResponse({"status": "error", "message": "Aucun établissement configuré."}, status=400)
    result = _activation_payload(school)
    return JsonResponse(result)
