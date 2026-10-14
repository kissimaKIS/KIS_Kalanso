from django.urls import path
from .views import (term_list, term_create, evaluation_create, evaluation_subjects, evaluation_results, evaluation_sheet_print, grade_entry, class_results, class_bulletins, grade_sheet_print, bulletin_config, class_ponctuel_summary, bulletin_lock_toggle)
from .views_passage import passage_list, passage_detail, passage_cap_decide, passage_director_validate, passage_print
from .views_teaching import teaching_list, teaching_create, teaching_delete
from .teacher_subject_views import teacher_subjects, teacher_subject_delete
from .views_catalog import (school_year_catalog, school_year_catalog_validate, level_subjects, preschool_subjects_copy, level_subject_edit, level_subject_toggle,
                           track_subjects, track_subject_edit, track_subject_toggle, track_edit, subject_edit, subject_add)

from .views_mobile import mobile_home, mobile_package_download, mobile_submission_upload, mobile_submission_detail, mobile_submission_apply, mobile_submission_cancel

urlpatterns = [
    path("pedagogie/saisie-mobile/", mobile_home, name="mobile_home"),
    path("pedagogie/saisie-mobile/paquet/", mobile_package_download, name="mobile_package_download"),
    path("pedagogie/saisie-mobile/charger/", mobile_submission_upload, name="mobile_submission_upload"),
    path("pedagogie/saisie-mobile/depots/<int:pk>/", mobile_submission_detail, name="mobile_submission_detail"),
    path("pedagogie/saisie-mobile/depots/<int:pk>/valider/", mobile_submission_apply, name="mobile_submission_apply"),
    path("pedagogie/saisie-mobile/depots/<int:pk>/abandonner/", mobile_submission_cancel, name="mobile_submission_cancel"),
    path("pedagogie/terms/", term_list, name="term_list"),
    path("pedagogie/passages/", passage_list, name="passage_list"),
    path("pedagogie/passages/classes/<int:classe_id>/", passage_detail, name="passage_detail"),
    path("pedagogie/passages/<int:passage_id>/cap/", passage_cap_decide, name="passage_cap_decide"),
    path("pedagogie/passages/<int:passage_id>/directeur/", passage_director_validate, name="passage_director_validate"),
    path("pedagogie/passages/<int:passage_id>/print/", passage_print, name="passage_print"),
    path("pedagogie/terms/add/", term_create, name="term_create"),
    path("pedagogie/evaluations/add/", evaluation_create, name="evaluation_create"),
    path("pedagogie/evaluations/subjects/", evaluation_subjects, name="evaluation_subjects"),
    path("pedagogie/evaluations/<int:evaluation_id>/results/", evaluation_results, name="evaluation_results"),
    path("pedagogie/evaluations/<int:evaluation_id>/grades/print/<int:subject_id>/", evaluation_sheet_print, name="evaluation_sheet_print"),
    path("pedagogie/enrollments/<int:enrollment_id>/terms/<int:term_id>/grades/", grade_entry, name="grade_entry"),
    path("pedagogie/classes/<int:classe_id>/bulletin-config/", bulletin_config, name="bulletin_config"),
    path("pedagogie/classes/<int:classe_id>/terms/<int:term_id>/results/", class_results, name="class_results"),
    path("pedagogie/classes/<int:classe_id>/terms/<int:term_id>/bulletins/", class_bulletins, name="class_bulletins"),
    path("pedagogie/classes/<int:classe_id>/terms/<int:term_id>/bulletins/verrou/", bulletin_lock_toggle, name="bulletin_lock_toggle"),
    path("pedagogie/classes/<int:classe_id>/terms/<int:term_id>/bulletin-ponctuel/", class_ponctuel_summary, name="class_ponctuel_summary"),
    path("pedagogie/classes/<int:classe_id>/terms/<int:term_id>/grades/print/<int:subject_id>/", grade_sheet_print, name="grade_sheet_print"),
    path("pedagogie/affectations/", teaching_list, name="teaching_list"),
    path("pedagogie/affectations/add/", teaching_create, name="teaching_create"),
    path("pedagogie/affectations/<int:pk>/delete/", teaching_delete, name="teaching_delete"),
    path("pedagogie/enseignants/<int:teacher_id>/matieres/", teacher_subjects, name="teacher_subjects"),
    path("pedagogie/enseignants/matieres/<int:pk>/delete/", teacher_subject_delete, name="teacher_subject_delete"),
    path("pedagogie/school-year/<int:pk>/catalogue/", school_year_catalog, name="school_year_catalog"),
    path("pedagogie/school-year/<int:pk>/catalogue/valider/", school_year_catalog_validate, name="school_year_catalog_validate"),
    path("pedagogie/referentiel/niveaux/<int:pk>/matieres/", level_subjects, name="level_subjects"),
    path("pedagogie/referentiel/niveaux/<int:pk>/matieres/copier/", preschool_subjects_copy, name="preschool_subjects_copy"),
    path("subjects/add/", subject_add, name="subject_add"),
    path("pedagogie/referentiel/matieres/<int:pk>/modifier/", subject_edit, name="subject_edit"),
    path("pedagogie/referentiel/niveaux/matieres/<int:pk>/modifier/", level_subject_edit, name="level_subject_edit"),
    path("pedagogie/referentiel/niveaux/matieres/<int:pk>/activer/", level_subject_toggle, name="level_subject_toggle"),
    path("pedagogie/referentiel/parcours/<int:pk>/modifier/", track_edit, name="track_edit"),
    path("pedagogie/referentiel/parcours/<int:pk>/matieres/", track_subjects, name="track_subjects"),
    path("pedagogie/referentiel/parcours/matieres/<int:pk>/modifier/", track_subject_edit, name="track_subject_edit"),
    path("pedagogie/referentiel/parcours/matieres/<int:pk>/activer/", track_subject_toggle, name="track_subject_toggle"),
]
