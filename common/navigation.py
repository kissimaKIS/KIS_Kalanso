"""Bouton « Retour » cohérent sur toutes les pages (retours du 08/10).

Le bouton ne s'appuie plus sur l'historique du navigateur (qui, après un
formulaire enregistré, ramène sur le formulaire ou sur une autre section) mais
sur un fil de navigation hiérarchique tenu en session :

- ouvrir une page d'entrée de menu (Classes, Encaissements…) repart de zéro ;
- ouvrir une page ajoute une étape ; revenir sur une page déjà dans le fil
  supprime les étapes suivantes ;
- un formulaire enregistré sort du fil.

Exemple : Classes → 1re année → fiche d'Ousmane → Ajuster la situation →
(enregistrer) → fiche d'Ousmane : « Retour » ramène à la 1re année, puis
à la liste des classes.
"""
from django.urls import Resolver404, resolve

SESSION_KEY = "kis_nav"
MAX_STEPS = 15
ROOTS = {
    "dashboard", "dashboard_page", "announcement_list", "arrears_import", "attendance_list", "backup_home",
    "budget_list", "classe_list", "correction_log", "debt_report", "discipline_list", "document_list",
    "enrollment_create", "family_list", "fee_type_list", "hourly_monthly_statement", "invoice_list", "mobile_home",
    "option_lists", "other_personnel_list", "other_personnel_payment_list", "passage_list", "payment_list",
    "permanent_annual_statement", "school_year_list", "staff_attendance_list", "student_duplicates",
    "student_list", "teacher_list", "teacher_payment_list", "teaching_list", "term_list", "user_list",
}
IGNORED = {"login", "logout", "startup", "bootstrap_admin", "license_activation", "license_check", "access_denied"}


def _url_name(path):
    try:
        return resolve(path).url_name
    except Resolver404:
        return None


def _trackable(request):
    if request.method != "GET":
        return False
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.headers.get("HX-Request"):
        return False
    if request.GET.get("modal"):
        return False
    return not request.path.startswith(("/static/", "/media/"))


class NavigationHistoryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.kis_back_url = None
        name = _url_name(request.path)
        track = _trackable(request) and hasattr(request, "session") and name and name not in IGNORED
        stack = list(request.session.get(SESSION_KEY, [])) if track else []
        if track and name not in ROOTS:
            paths = [step[0] for step in stack]
            if request.path in paths:
                index = paths.index(request.path)
                request.kis_back_url = stack[index - 1][1] if index > 0 else None
            elif stack:
                request.kis_back_url = stack[-1][1]
        response = self.get_response(request)
        # Un formulaire enregistré (POST suivi d'une redirection) sort du fil : après
        # « Ajuster la situation » ou un encaissement, Retour ne ramène pas au formulaire.
        if (request.method == "POST" and 300 <= response.status_code < 400 and hasattr(request, "session")
                and request.session.get(SESSION_KEY)):
            request.session[SESSION_KEY] = [s for s in request.session[SESSION_KEY] if s[0] != request.path]
        if track and response.status_code == 200 and "text/html" in response.get("Content-Type", ""):
            entry = [request.path, request.get_full_path()]
            if name in ROOTS:
                stack = [entry]
            else:
                paths = [step[0] for step in stack]
                if request.path in paths:
                    stack = stack[:paths.index(request.path)] + [entry]
                else:
                    stack = (stack + [entry])[-MAX_STEPS:]
            request.session[SESSION_KEY] = stack
        return response


def back_url(request):
    return {"kis_back_url": getattr(request, "kis_back_url", None)}
