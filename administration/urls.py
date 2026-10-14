from django.urls import path
from .views.auth_views import login_view, logout_view, bootstrap_admin
from .views.school_views import school_create, school_edit
from .views.school_year_views import school_year_create, school_year_list, school_year_activate, school_year_close
from .views.class_views import classe_list, add_classe, classe_detail, classe_modal
from .views.student_views import enrollment_create, enrollment_fees, add_student, student_edit, import_students, student_list, student_detail, student_list_pdf, certificat_frequentation_pdf, carte_identite_pdf, cartes_identite_classe_pdf, fiche_scolaire_pdf, releve_notes_pdf, certificat_transfert_pdf, fiche_inscription_vierge_pdf, fiche_inscription_pdf, matricule_generate
from .views.teacher_views import teacher_list, teacher_create, teacher_edit, teacher_pdf, teacher_payment_list, teacher_payment_create, teacher_payment_pdf, other_personnel_list, other_personnel_pdf, other_personnel_create, other_personnel_edit, other_personnel_payment_list, other_personnel_payment_create, other_personnel_payment_pdf, import_teachers, import_other_personnel
from .views.correction_views import correction, correction_log, student_duplicates, student_merge, student_merge_pick
from .views.salary_views import salary_cancel, salary_payslip_pdf
from .views.user_views import user_list, user_create, user_edit, user_toggle
from .views.initial_configuration_views import initial_configuration
from .views.salary_reports_views import permanent_annual_statement, hourly_monthly_statement

urlpatterns = [
    path("corrections/journal/", correction_log, name="correction_log"),
    path("students/matricules/", matricule_generate, name="matricule_generate"),
    path("corrections/doublons/", student_duplicates, name="student_duplicates"),
    path("corrections/fusion/<int:student_id>/", student_merge_pick, name="student_merge_pick"),
    path("corrections/fusion/<int:keep_id>/<int:drop_id>/", student_merge, name="student_merge"),
    path("corrections/<str:kind>/<int:pk>/", correction, name="correction"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("setup/", bootstrap_admin, name="bootstrap_admin"),
    path("initial-configuration/", initial_configuration, name="initial_configuration"),
    path("school/create/", school_create, name="school_create"),
    path("school/<int:pk>/edit/", school_edit, name="school_edit"),
    path("school-years/", school_year_list, name="school_year_list"),
    path("school-year/create/", school_year_create, name="school_year_create"),
    path("school-year/<int:pk>/activate/", school_year_activate, name="school_year_activate"),
    path("school-year/<int:pk>/close/", school_year_close, name="school_year_close"),
    path("enrollments/new/", enrollment_create, name="enrollment_create"),
    path("enrollments/fees/", enrollment_fees, name="enrollment_fees"),
    path("classes/", classe_list, name="classe_list"),
    path("classes/add/", add_classe, name="add_classe"),
    path("classes/modal/new/", classe_modal, name="classe_modal"),
    path("classes/<int:classe_id>/", classe_detail, name="classe_detail"),
    path("classes/<int:classe_id>/students/add/", add_student, name="add_student"),
    path("classes/<int:classe_id>/students/import/", import_students, name="import_students"),
    path("students/", student_list, name="student_list"),
    path("students/pdf/", student_list_pdf, name="student_list_pdf"),
    path("students/<int:student_id>/", student_detail, name="student_detail"),
    path("students/<int:student_id>/edit/", student_edit, name="student_edit"),
    path("enrollments/<int:enrollment_id>/certificat-frequentation/", certificat_frequentation_pdf, name="certificat_frequentation_pdf"),
    path("enrollments/<int:enrollment_id>/carte-identite/", carte_identite_pdf, name="carte_identite_pdf"),
    path("enrollments/<int:enrollment_id>/releve-notes/", releve_notes_pdf, name="releve_notes_pdf"),
    path("enrollments/<int:enrollment_id>/certificat-transfert/", certificat_transfert_pdf, name="certificat_transfert_pdf"),
    path("students/<int:student_id>/fiche-scolaire/", fiche_scolaire_pdf, name="fiche_scolaire_pdf"),
    path("enrollments/fiche-inscription/vierge/", fiche_inscription_vierge_pdf, name="fiche_inscription_vierge_pdf"),
    path("enrollments/<int:enrollment_id>/fiche-inscription/", fiche_inscription_pdf, name="fiche_inscription_pdf"),
    path("classes/<int:classe_id>/cartes-identite/", cartes_identite_classe_pdf, name="cartes_identite_classe_pdf"),
    path("teachers/", teacher_list, name="teacher_list"),
    path("teachers/pdf/", teacher_pdf, name="teacher_pdf"),
    path("teachers/payments/", teacher_payment_list, name="teacher_payment_list"),
    path("salaires/<str:kind>/annuler/", salary_cancel, name="salary_cancel"),
    path("salaires/<str:kind>/<int:pk>/bulletin/", salary_payslip_pdf, name="salary_payslip_pdf"),
    path("teachers/payments/add/", teacher_payment_create, name="teacher_payment_create"),
    path("teachers/payments/pdf/", teacher_payment_pdf, name="teacher_payment_pdf"),
    path("teachers/add/", teacher_create, name="teacher_create"),
    path("teachers/import/", import_teachers, name="import_teachers"),
    path("teachers/<int:pk>/edit/", teacher_edit, name="teacher_edit"),
    path("other-personnel/", other_personnel_list, name="other_personnel_list"),
    path("other-personnel/pdf/", other_personnel_pdf, name="other_personnel_pdf"),
    path("other-personnel/add/", other_personnel_create, name="other_personnel_create"),
    path("other-personnel/import/", import_other_personnel, name="import_other_personnel"),
    path("other-personnel/<int:pk>/edit/", other_personnel_edit, name="other_personnel_edit"),
    path("other-personnel/payments/", other_personnel_payment_list, name="other_personnel_payment_list"),
    path("other-personnel/payments/add/", other_personnel_payment_create, name="other_personnel_payment_create"),
    path("other-personnel/payments/pdf/", other_personnel_payment_pdf, name="other_personnel_payment_pdf"),
    path("salaires/etat-annuel/", permanent_annual_statement, name="permanent_annual_statement"),
    path("salaires/etat-horaire/", hourly_monthly_statement, name="hourly_monthly_statement"),
    path("users/", user_list, name="user_list"),
    path("users/add/", user_create, name="user_create"),
    path("users/<int:pk>/edit/", user_edit, name="user_edit"),
    path("users/<int:pk>/toggle/", user_toggle, name="user_toggle"),
]
