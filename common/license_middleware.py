from django.shortcuts import redirect

from .license import license_is_active


class LicenseMiddleware:
    """Bloque l'utilisation après le pilote tant qu'une licence valide n'est pas activée."""

    EXEMPT_URL_NAMES = {
        "login",
        "logout",
        "bootstrap_admin",
        "initial_configuration",
        "license_activation",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if license_is_active() or not request.user.is_authenticated:
            return None
        url_name = getattr(getattr(request, "resolver_match", None), "url_name", None)
        if url_name in self.EXEMPT_URL_NAMES:
            return None
        return redirect("license_activation")
