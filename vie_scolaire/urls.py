from django.urls import path
from .views_pointage import api_pointage_package, api_pointage_upload, pointage_home, pointage_package, staff_badges_pdf
from .views import attendance_list, attendance_mark, attendance_week_pdf, discipline_list, discipline_create, discipline_students, staff_attendance_list
urlpatterns=[
 path("vie-scolaire/pointage/", pointage_home, name="pointage_home"),
 path("vie-scolaire/pointage/paquet/", pointage_package, name="pointage_package"),
 path("personnel/badges/", staff_badges_pdf, name="staff_badges_pdf"),
 path("api/pointage/paquet/", api_pointage_package, name="api_pointage_package"),
 path("api/pointage/envoi/", api_pointage_upload, name="api_pointage_upload"),
 path("vie-scolaire/presences/", attendance_list, name="attendance_list"),
 path("vie-scolaire/presences/pdf/", attendance_week_pdf, name="attendance_week_pdf"),
 path("vie-scolaire/classes/<int:classe_id>/presences/", attendance_mark, name="attendance_mark"),
 path("vie-scolaire/pointage-personnel/", staff_attendance_list, name="staff_attendance_list"),
 path("vie-scolaire/discipline/", discipline_list, name="discipline_list"),
 path("vie-scolaire/enrollments/<int:enrollment_id>/discipline/add/", discipline_create, name="discipline_create"),
 path("vie-scolaire/discipline/classes/<int:classe_id>/students/", discipline_students, name="discipline_students"),
]
