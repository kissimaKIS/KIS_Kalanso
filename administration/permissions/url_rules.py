"""Permission requise pour chaque page, indexée par nom d'URL.

Toute URL nommée de l'application doit figurer ici (ou dans PUBLIC_URLS) :
une URL absente est réservée aux profils disposant de toutes les
permissions. Le test ``test_every_url_has_a_rule`` le vérifie.

Une valeur peut être une permission ou un tuple de permissions (l'une
d'entre elles suffit).
"""
from .access import (
    BUDGET_MANAGE, BULLETINS_PRINT, DATA_CORRECT, COMMUNICATION_MANAGE, DASHBOARD_VIEW,
    FINANCE_COLLECT, FINANCE_MANAGE, GRADES_ENTER, PEDAGOGY_MANAGE,
    PERSONNEL_MANAGE, SALARIES_MANAGE, SCHOOL_CONFIGURE, SCHOOL_LIFE_MANAGE,
    STUDENTS_MANAGE, STUDENTS_VIEW, TEACHINGS_VIEW, USERS_MANAGE,
)

# Pages accessibles sans contrôle de rôle (authentification gérée par la vue).
PUBLIC_URLS = {
    "login", "logout", "bootstrap_admin", "startup", "set_viewed_year",
    "license_activation", "license_check", "access_denied",
    # Téléphones de pointage : authentifiés par la clé de pointage (voir vie_scolaire/views_pointage.py).
    "api_pointage_package", "api_pointage_upload",
}

URL_PERMISSIONS = {
    # Pilotage
    "dashboard": DASHBOARD_VIEW,
    "budget_list": BUDGET_MANAGE,
    "budget_create": BUDGET_MANAGE,
    "import_budget": BUDGET_MANAGE,
    "budget_pdf": BUDGET_MANAGE,
    "cash_statement_pdf": BUDGET_MANAGE,
    "teacher_followup": PEDAGOGY_MANAGE,
    "teacher_evaluate": PEDAGOGY_MANAGE,

    # Administration : établissement et années scolaires
    "initial_configuration": SCHOOL_CONFIGURE,
    "school_create": SCHOOL_CONFIGURE,
    "school_edit": SCHOOL_CONFIGURE,
    "school_year_list": SCHOOL_CONFIGURE,
    "school_year_create": SCHOOL_CONFIGURE,
    "school_year_activate": SCHOOL_CONFIGURE,
    "school_year_close": SCHOOL_CONFIGURE,

    # Sauvegarde et restauration
    "backup_home": SCHOOL_CONFIGURE,
    "network_settings": SCHOOL_CONFIGURE,
    "network_shortcut": SCHOOL_CONFIGURE,
    "network_stop": SCHOOL_CONFIGURE,
    "backup_create": SCHOOL_CONFIGURE,
    "backup_settings": SCHOOL_CONFIGURE,
    "backup_download": SCHOOL_CONFIGURE,
    "backup_restore": SCHOOL_CONFIGURE,
    "backup_restore_upload": SCHOOL_CONFIGURE,

    # Utilisateurs
    "user_list": USERS_MANAGE,
    "user_create": USERS_MANAGE,
    "user_edit": USERS_MANAGE,
    "user_toggle": USERS_MANAGE,

    # Listes par option (cantine, transport, uniforme) : scolarité ou caisse
    "option_lists": (STUDENTS_MANAGE, FINANCE_COLLECT),
    "family_list": FINANCE_COLLECT,
    "arrears_import": FINANCE_MANAGE,
    "arrears_quick": FINANCE_MANAGE,
    "arrears_template": FINANCE_MANAGE,
    "prior_balance_add": FINANCE_MANAGE,
    "family_list_pdf": FINANCE_COLLECT,
    "option_list_pdf": (STUDENTS_MANAGE, FINANCE_COLLECT),

    # Corrections (direction)
    "correction": DATA_CORRECT,
    "correction_log": DATA_CORRECT,
    "student_duplicates": DATA_CORRECT,
    "matricule_generate": DATA_CORRECT,
    "salary_cancel": DATA_CORRECT,
    "salary_payslip_pdf": SALARIES_MANAGE,
    "student_merge_pick": DATA_CORRECT,
    "student_merge": DATA_CORRECT,

    # Scolarité
    "classe_list": STUDENTS_VIEW,
    "classe_detail": STUDENTS_VIEW,
    "student_list": STUDENTS_VIEW,
    "student_list_pdf": STUDENTS_VIEW,
    "student_detail": STUDENTS_VIEW,
    "enrollment_create": STUDENTS_MANAGE,
    "enrollment_fees": STUDENTS_MANAGE,
    "add_classe": STUDENTS_MANAGE,
    "classe_modal": STUDENTS_MANAGE,
    "add_student": STUDENTS_MANAGE,
    "import_students": STUDENTS_MANAGE,
    "student_edit": STUDENTS_MANAGE,
    "certificat_frequentation_pdf": STUDENTS_MANAGE,
    "certificat_transfert_pdf": STUDENTS_MANAGE,
    "releve_notes_pdf": STUDENTS_MANAGE,
    "fiche_scolaire_pdf": STUDENTS_MANAGE,
    "fiche_inscription_vierge_pdf": STUDENTS_MANAGE,
    "fiche_inscription_pdf": STUDENTS_MANAGE,
    "carte_identite_pdf": STUDENTS_MANAGE,
    "cartes_identite_classe_pdf": STUDENTS_MANAGE,

    # Personnel
    "teacher_list": PERSONNEL_MANAGE,
    "teacher_pdf": PERSONNEL_MANAGE,
    "teacher_create": PERSONNEL_MANAGE,
    "import_teachers": PERSONNEL_MANAGE,
    "teacher_edit": PERSONNEL_MANAGE,
    "other_personnel_list": PERSONNEL_MANAGE,
    "other_personnel_pdf": PERSONNEL_MANAGE,
    "other_personnel_create": PERSONNEL_MANAGE,
    "import_other_personnel": PERSONNEL_MANAGE,
    "other_personnel_edit": PERSONNEL_MANAGE,

    # Salaires (finance du personnel)
    "teacher_payment_list": SALARIES_MANAGE,
    "teacher_payment_create": SALARIES_MANAGE,
    "teacher_payment_pdf": SALARIES_MANAGE,
    "other_personnel_payment_list": SALARIES_MANAGE,
    "other_personnel_payment_create": SALARIES_MANAGE,
    "other_personnel_payment_pdf": SALARIES_MANAGE,
    "permanent_annual_statement": SALARIES_MANAGE,
    "hourly_monthly_statement": SALARIES_MANAGE,

    # Finance (hors budget)
    "fee_type_list": FINANCE_MANAGE,
    "fee_type_create": FINANCE_MANAGE,
    "fee_type_create_for_class": FINANCE_MANAGE,
    "fee_components": FINANCE_MANAGE,
    "invoice_ventilation": FINANCE_COLLECT,
    "invoice_list": FINANCE_MANAGE,
    "invoice_create": FINANCE_MANAGE,
    "debt_report": FINANCE_MANAGE,
    "debt_report_pdf": FINANCE_MANAGE,
    "financial_adjustment": FINANCE_MANAGE,
    "payment_start": FINANCE_COLLECT,
    "payment_create": FINANCE_COLLECT,
    "grouped_payment": FINANCE_COLLECT,
    "payment_done": FINANCE_COLLECT,
    "batch_receipt_pdf": FINANCE_COLLECT,
    "receipts_print_pdf": FINANCE_COLLECT,
    "family_statement_pdf": FINANCE_COLLECT,
    "payment_list": FINANCE_COLLECT,
    "receipt_pdf": FINANCE_COLLECT,
    "invoice_statement_pdf": FINANCE_COLLECT,

    # Pédagogie : saisie des notes (limitée à ses affectations pour un professeur)
    "term_list": (GRADES_ENTER, BULLETINS_PRINT),
    "class_results": GRADES_ENTER,
    "evaluation_results": GRADES_ENTER,
    "evaluation_sheet_print": GRADES_ENTER,
    "grade_sheet_print": GRADES_ENTER,
    "teaching_list": TEACHINGS_VIEW,

    # Saisie mobile des notes (lycée et centre)
    "mobile_home": PEDAGOGY_MANAGE,
    "mobile_package_download": PEDAGOGY_MANAGE,
    "mobile_submission_upload": PEDAGOGY_MANAGE,
    "mobile_submission_detail": PEDAGOGY_MANAGE,
    "mobile_submission_apply": PEDAGOGY_MANAGE,
    "mobile_submission_cancel": PEDAGOGY_MANAGE,

    # Pédagogie : organisation
    "grade_entry": PEDAGOGY_MANAGE,
    "term_create": PEDAGOGY_MANAGE,
    "evaluation_create": PEDAGOGY_MANAGE,
    "evaluation_subjects": PEDAGOGY_MANAGE,
    "bulletin_config": PEDAGOGY_MANAGE,
    "teaching_create": PEDAGOGY_MANAGE,
    "teaching_delete": PEDAGOGY_MANAGE,
    "teacher_subjects": PEDAGOGY_MANAGE,
    "teacher_subject_delete": PEDAGOGY_MANAGE,
    "passage_list": PEDAGOGY_MANAGE,
    "passage_detail": PEDAGOGY_MANAGE,
    "passage_cap_decide": PEDAGOGY_MANAGE,
    "passage_director_validate": PEDAGOGY_MANAGE,
    "passage_print": PEDAGOGY_MANAGE,
    "school_year_catalog": PEDAGOGY_MANAGE,
    "school_year_catalog_validate": PEDAGOGY_MANAGE,
    "level_subjects": PEDAGOGY_MANAGE,
    "preschool_subjects_copy": PEDAGOGY_MANAGE,
    "subject_add": PEDAGOGY_MANAGE,
    "subject_edit": PEDAGOGY_MANAGE,
    "level_subject_edit": PEDAGOGY_MANAGE,
    "level_subject_toggle": PEDAGOGY_MANAGE,
    "track_edit": PEDAGOGY_MANAGE,
    "track_subjects": PEDAGOGY_MANAGE,
    "track_subject_edit": PEDAGOGY_MANAGE,
    "track_subject_toggle": PEDAGOGY_MANAGE,

    # Bulletins
    "class_bulletins": BULLETINS_PRINT,
    "bulletin_lock_toggle": PEDAGOGY_MANAGE,
    "class_ponctuel_summary": BULLETINS_PRINT,
    "bulletin_pdf": BULLETINS_PRINT,
    "class_bulletins_pdf": BULLETINS_PRINT,
    "bulletin_ponctuel_pdf": BULLETINS_PRINT,
    "class_ponctuel_pdf": BULLETINS_PRINT,

    # Vie scolaire
    "attendance_list": SCHOOL_LIFE_MANAGE,
    "attendance_mark": SCHOOL_LIFE_MANAGE,
    "attendance_week_pdf": SCHOOL_LIFE_MANAGE,
    "pointage_home": SCHOOL_LIFE_MANAGE,
    "pointage_package": SCHOOL_LIFE_MANAGE,
    "staff_badges_pdf": (PERSONNEL_MANAGE, SCHOOL_LIFE_MANAGE),
    "staff_attendance_list": SCHOOL_LIFE_MANAGE,
    "discipline_list": SCHOOL_LIFE_MANAGE,
    "discipline_create": SCHOOL_LIFE_MANAGE,
    "discipline_students": SCHOOL_LIFE_MANAGE,

    # Communication & documents
    "announcement_list": COMMUNICATION_MANAGE,
    "announcement_create": COMMUNICATION_MANAGE,
    "announcement_update": COMMUNICATION_MANAGE,
    "announcement_whatsapp": COMMUNICATION_MANAGE,
    "announcement_delete": COMMUNICATION_MANAGE,
    "announcement_pdf": COMMUNICATION_MANAGE,
    "document_list": COMMUNICATION_MANAGE,
    "document_create": (COMMUNICATION_MANAGE, STUDENTS_MANAGE),
    "document_delete": (COMMUNICATION_MANAGE, STUDENTS_MANAGE),
    "document_students": (COMMUNICATION_MANAGE, STUDENTS_MANAGE),
}


def required_permissions(url_name):
    """Tuple des permissions acceptées pour une URL, ou None si publique."""
    if url_name in PUBLIC_URLS:
        return None
    rule = URL_PERMISSIONS.get(url_name)
    if rule is None:
        return ("__all__",)
    if isinstance(rule, str):
        return (rule,)
    return tuple(rule)
