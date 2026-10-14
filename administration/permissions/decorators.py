from django.contrib.auth.decorators import user_passes_test

from .access import user_has_permission


def permission_required(permission):
    """Protège une vue selon une permission métier."""
    return user_passes_test(
        lambda user: user_has_permission(user, permission),
        login_url="login",
    )
