"""Pointage par QR code (V8-8) : réglages, téléphones, synchronisation, badges."""
import datetime
import hmac
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from administration.models import OtherPersonnel, School, Teacher
from common import network
from vie_scolaire.models import PointageConfig, PointageScan
from vie_scolaire.services import pointage as svc

MAX_UPLOAD = 5 * 1024 * 1024


def _server_urls():
    config = network.load_config()
    if not network.is_server(config):
        return []
    return [f"http://{ip}:{config['port']}/" for ip in network.lan_addresses()]


def _school():
    return School.objects.filter(is_active=True).first()


@login_required
def pointage_home(request):
    config = PointageConfig.get()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "regen":
            config.regenerate_key()
            messages.success(request, "Nouvelle clé créée : rechargez le paquet sur chaque téléphone de pointage.")
        elif action == "settings":
            raw = (request.POST.get("staff_start_time") or "").strip()
            try:
                config.staff_start_time = datetime.time.fromisoformat(raw) if raw else None
            except ValueError:
                messages.error(request, "Heure invalide.")
            else:
                config.save(update_fields=["staff_start_time", "updated_at"])
                messages.success(request, "Réglage enregistré.")
        elif action == "upload":
            upload = request.FILES.get("file")
            if not upload:
                messages.error(request, "Choisissez le fichier « pointage_….json » envoyé par le téléphone.")
            elif upload.size > MAX_UPLOAD:
                messages.error(request, "Fichier trop volumineux.")
            else:
                try:
                    summary = svc.apply_export(svc.load_json(upload.read()))
                except (ValueError, UnicodeDecodeError) as exc:
                    messages.error(request, f"Relevé refusé : {exc}")
                else:
                    messages.success(request, "Relevé chargé : " + svc.summary_text(summary))
        return redirect("pointage_home")

    day_raw = request.GET.get("date") or ""
    try:
        day = datetime.date.fromisoformat(day_raw) if day_raw else timezone.localdate()
    except ValueError:
        day = timezone.localdate()
    scans = PointageScan.objects.filter(scanned_at__date=day).select_related("student", "teacher", "personnel")
    counts = scans.aggregate(
        total=Count("id"),
        staff=Count("teacher", distinct=True) + Count("personnel", distinct=True),
        students=Count("student", distinct=True),
        unknown=Count("id", filter=Q(person_type=PointageScan.Person.UNKNOWN)),
    )
    devices = (PointageScan.objects.values("device_id").annotate(last=Max("received_at"), n=Count("id")).order_by("-last")[:10])
    setup = []
    for url in _server_urls():
        payload = f"KIS-POINTAGE|{url}|{config.api_key}"
        from common.views_network import _qr_svg
        setup.append({"url": url, "qr": _qr_svg(payload, size=170)})
    return render(request, "vie_scolaire/pointage.html", {
        "config": config, "day": day, "scans": scans[:200], "counts": counts, "devices": devices, "setup": setup,
        "server_mode": network.is_server(),
    })


@login_required
def pointage_package(request):
    """Paquet de pointage à envoyer au téléphone (WhatsApp, Bluetooth, câble…)."""
    data = svc.build_package(_school(), _server_urls())
    response = HttpResponse(json.dumps(data, ensure_ascii=False), content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="paquet_pointage_{timezone.localdate():%Y%m%d}.json"'
    return response


@login_required
def staff_badges_pdf(request):
    from administration.badge_personnel_pdf import badge_items, render_badges_pdf
    from administration.models import SchoolYear
    kind = request.GET.get("type", "all")
    teachers = Teacher.objects.filter(is_active=True).order_by("last_name", "first_name") if kind in ("all", "teacher") else Teacher.objects.none()
    personnel = OtherPersonnel.objects.filter(is_active=True).order_by("last_name", "first_name") if kind in ("all", "staff") else OtherPersonnel.objects.none()
    if request.GET.get("id", "").isdigit():
        teachers = teachers.filter(pk=request.GET["id"])
        personnel = personnel.filter(pk=request.GET["id"])
    year = SchoolYear.objects.filter(is_active=True).first()
    pdf = render_badges_pdf(badge_items(teachers, personnel), _school(), year.name if year else "")
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="badges_personnel.pdf"'
    return response


# ---------------------------------------------------------------- API des téléphones (réseau local)
def _key_ok(request):
    given = request.headers.get("X-KIS-Cle") or request.GET.get("cle") or ""
    return bool(given) and hmac.compare_digest(given, PointageConfig.get().api_key)


def api_pointage_package(request):
    if not _key_ok(request):
        return JsonResponse({"error": "Clé de pointage invalide : rechargez le paquet depuis KIS Kalanso."}, status=403)
    return JsonResponse(svc.build_package(_school(), _server_urls()), json_dumps_params={"ensure_ascii": False})


@csrf_exempt
def api_pointage_upload(request):
    if request.method != "POST":
        return JsonResponse({"error": "Méthode non autorisée."}, status=405)
    if not _key_ok(request):
        return JsonResponse({"error": "Clé de pointage invalide : rechargez le paquet depuis KIS Kalanso."}, status=403)
    if len(request.body) > MAX_UPLOAD:
        return JsonResponse({"error": "Relevé trop volumineux."}, status=413)
    try:
        summary = svc.apply_export(svc.load_json(request.body))
    except (ValueError, UnicodeDecodeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    summary["message"] = svc.summary_text(summary)
    return JsonResponse(summary)
