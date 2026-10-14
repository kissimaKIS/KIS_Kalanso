"""Année consultée (retours du 08/10, test B07).

Par défaut, KIS affiche l'année active. Le sélecteur en haut de l'écran permet
de consulter une autre année (clôturée, ou année reprise) : les listes —
classes, élèves, finances, présences, bulletins, tableau de bord… — montrent
alors cette année, en lecture seule. Tant qu'une année passée est consultée,
les enregistrements sont refusés, sauf ceux qui ont un sens sur une année
passée (encaisser un reste dû, corrections de la direction) ; un bandeau
rappelle l'année consultée et permet de revenir à l'année en cours.
"""
import contextvars

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import Resolver404, resolve
from django.utils.http import url_has_allowed_host_and_scheme

SESSION_KEY = "kis_viewed_year"
_request = contextvars.ContextVar("kis_request", default=None)

# Enregistrements permis pendant la consultation d'une année passée.
ALLOWED_WHEN_PAST = {
    "set_viewed_year", "logout", "login", "grouped_payment", "payment_create", "correction", "student_merge",
    "arrears_import", "arrears_quick", "prior_balance_add", "backup_create", "backup_restore", "backup_restore_upload",
    "backup_settings",
}


_MISSING = object()


def active_year():
    """Année active, mémorisée le temps d'une requête (évite des requêtes répétées)."""
    from administration.models import SchoolYear
    request = _request.get()
    cached = getattr(request, "_kis_active_year", _MISSING) if request is not None else _MISSING
    if cached is not _MISSING:
        return cached
    year = SchoolYear.objects.filter(is_active=True).select_related("school").first()
    if request is not None:
        request._kis_active_year = year
    return year


def viewed_year(request=None):
    """Année à afficher : l'année choisie dans le sélecteur, sinon l'année active."""
    from administration.models import SchoolYear
    request = request or _request.get()
    active = active_year()
    if request is not None and hasattr(request, "session"):
        cached = getattr(request, "_kis_viewed_year", None)
        if cached is not None:
            return cached
        if not request.session.get(SESSION_KEY):
            return active
        year_id = request.session.get(SESSION_KEY)
        if year_id and (not active or year_id != active.pk):
            year = SchoolYear.objects.filter(pk=year_id).select_related("school").first()
            if year:
                request._kis_viewed_year = year
                return year
    return active


def viewing_past(request):
    year, active = viewed_year(request), active_year()
    return bool(year and active and year.pk != active.pk)


class ViewedYearMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _request.set(request)
        try:
            if request.method == "POST" and getattr(request, "user", None) and request.user.is_authenticated:
                try:
                    name = resolve(request.path).url_name
                except Resolver404:
                    name = None
                if name not in ALLOWED_WHEN_PAST and viewing_past(request):
                    messages.warning(request, f"Vous consultez l'année {viewed_year(request).name} : rien n'a été "
                                              "enregistré. Revenez à l'année en cours pour modifier.")
                    return redirect(request.get_full_path())
            return self.get_response(request)
        finally:
            _request.reset(token)


def set_viewed_year(request):
    from administration.models import SchoolYear
    value = request.POST.get("year") or request.GET.get("year") or ""
    active = active_year()
    if value == "active" or (active and value == str(active.pk)):
        request.session.pop(SESSION_KEY, None)
    else:
        year = SchoolYear.objects.filter(pk=value).first() if value.isdigit() else None
        if year:
            request.session[SESSION_KEY] = year.pk
    target = request.POST.get("next") or request.GET.get("next") or "/"
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        target = "/"
    return redirect(target)


def year_context(request):
    from administration.models import SchoolYear
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    year = viewed_year(request)
    active = active_year()
    choices = list(SchoolYear.objects.order_by("-start_date")) if request.method == "GET" else []
    return {
        "kis_viewed_year": year,
        "kis_viewing_past": bool(year and active and year.pk != active.pk) or bool(year and not active),
        "kis_year_choices": choices,
    }
