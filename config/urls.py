from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve
from django.conf import settings
from django.conf.urls.static import static
from administration.views.auth_views import login_view
from pilotage.views.startup_views import startup

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", startup, name="startup"),
    path("", include("common.urls")),
    path("", include("administration.urls")),
    path("", include("finance.urls")),
    path("", include("pedagogie.urls")),
    path("", include("pilotage.urls")),
    path("", include("vie_scolaire.urls")),
    path("", include("communication.urls")),
    path("", include("documents.urls")),
]
# Photos et logos : application locale mono-poste, servis par Django même
# hors mode DEBUG (aucun serveur web séparé n'est installé).
urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
