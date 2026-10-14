from django.conf import settings
from django.shortcuts import render

from .access import ALL_PERMISSIONS, user_permissions
from .url_rules import required_permissions


def deny(request, message=None):
    """Réponse uniforme en cas d'accès refusé (page complète ou fenêtre modale)."""
    context = {
        "denied_message": message or "Votre rôle ne vous permet pas d'ouvrir cette page.",
    }
    template = "common/access_denied.html"
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        template = "common/_access_denied_modal.html"
    return render(request, template, context, status=403)


def user_can_open(user, url_name):
    required = required_permissions(url_name)
    if required is None:
        return True
    permissions = user_permissions(user)
    if required == ("__all__",):
        return permissions >= ALL_PERMISSIONS
    return any(permission in permissions for permission in required)


class RoleAccessMiddleware:
    """Applique la matrice des rôles à toutes les pages de l'application.

    Les vues gardent leur ``login_required`` : un visiteur non connecté est
    toujours renvoyé vers l'écran de connexion. Ce middleware n'intervient que
    pour un utilisateur connecté qui tente d'ouvrir une page hors de son rôle.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        if match is None:
            return None
        if match.url_name is None and request.path.startswith(settings.MEDIA_URL):
            # Photos et logos (servis par Django en mode développement).
            return None
        if match.namespace == "admin":
            # L'administration Django technique a son propre contrôle (is_staff).
            return None
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        if user_can_open(user, match.url_name):
            return None
        return deny(request)
