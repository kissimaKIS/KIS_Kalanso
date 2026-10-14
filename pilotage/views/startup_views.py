from django.shortcuts import redirect

from administration.models import School, SchoolYear, User
from administration.permissions import user_has_permission
from administration.permissions.access import DASHBOARD_VIEW, SCHOOL_CONFIGURE
from administration.permissions.middleware import deny


def startup(request):
    # Premier lancement : ne jamais afficher l'écran de connexion.
    # Tant qu'aucun compte n'existe, ouvrir directement la création du
    # premier administrateur. Après création du compte, le parcours continue
    # vers la configuration initiale.
    if not User.objects.exists():
        return redirect("bootstrap_admin")

    # Utilisation normale : l'authentification reste obligatoire.
    if not request.user.is_authenticated:
        return redirect("login")

    can_configure = user_has_permission(request.user, SCHOOL_CONFIGURE)
    if not School.objects.filter(is_active=True).exists():
        if not can_configure:
            return deny(request, "L'établissement n'est pas encore configuré. Contactez l'administrateur.")
        return redirect("initial_configuration")
    school = School.objects.filter(is_active=True).order_by("id").first()
    if school and not SchoolYear.objects.filter(school=school, is_active=True, is_closed=False).exists():
        if not can_configure:
            return deny(request, "Aucune année scolaire n'est ouverte. Contactez l'administrateur.")
        # L'établissement choisit explicitement son calendrier au premier lancement.
        return redirect("school_year_create")
    if not user_has_permission(request.user, DASHBOARD_VIEW):
        return redirect("access_denied")
    return redirect("dashboard")
