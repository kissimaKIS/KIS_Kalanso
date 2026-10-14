from django.urls import path
from .views import bulletin_pdf, class_bulletins_pdf, bulletin_ponctuel_pdf, class_ponctuel_pdf
from .views_license import license_activation, license_check
from .views_access import access_denied
from .views_network import network_settings, network_shortcut, network_stop
from .views_backup import backup_home, backup_create, backup_download, backup_restore, backup_restore_upload, backup_settings

from .years import set_viewed_year

urlpatterns = [
    path("annee-consultee/", set_viewed_year, name="set_viewed_year"),
    path("bulletin/<int:enrollment_id>/<int:term_id>/", bulletin_pdf, name="bulletin_pdf"),
    path("bulletins/classe/<int:classe_id>/<int:term_id>/", class_bulletins_pdf, name="class_bulletins_pdf"),
    path("bulletin-ponctuel/<int:enrollment_id>/<int:term_id>/", bulletin_ponctuel_pdf, name="bulletin_ponctuel_pdf"),
    path("bulletins-ponctuels/classe/<int:classe_id>/<int:term_id>/", class_ponctuel_pdf, name="class_ponctuel_pdf"),
    path("licence/", license_activation, name="license_activation"),
    path("licence/check/", license_check, name="license_check"),
    path("acces-refuse/", access_denied, name="access_denied"),
    path("reseau/", network_settings, name="network_settings"),
    path("reseau/raccourci/", network_shortcut, name="network_shortcut"),
    path("reseau/arreter/", network_stop, name="network_stop"),
    path("sauvegardes/", backup_home, name="backup_home"),
    path("sauvegardes/creer/", backup_create, name="backup_create"),
    path("sauvegardes/parametres/", backup_settings, name="backup_settings"),
    path("sauvegardes/importer/", backup_restore_upload, name="backup_restore_upload"),
    path("sauvegardes/<str:name>/telecharger/", backup_download, name="backup_download"),
    path("sauvegardes/<str:name>/restaurer/", backup_restore, name="backup_restore"),
]
