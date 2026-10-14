from django.contrib.auth.decorators import login_required

from administration.permissions.middleware import deny


@login_required
def access_denied(request):
    return deny(request, "Aucun espace n'est encore disponible pour votre rôle. Contactez l'administrateur de l'établissement.")
