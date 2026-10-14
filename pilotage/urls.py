from django.urls import path
from .views.dashboard_views import dashboard
from .views.budget_views import budget_list,budget_create,budget_pdf,cash_statement_pdf,import_budget
from .views.teacher_views import teacher_followup,teacher_evaluate
urlpatterns = [
    path("dashboard/", dashboard, name="dashboard"),

    path(
        "budget/",
        budget_list,
        name="budget_list",
    ),
    path(
        "budget/add/",
        budget_create,
        name="budget_create",
    ),
    path("budget/import/", import_budget, name="import_budget"),
    path("budget/pdf/", budget_pdf, name="budget_pdf"),
    path("budget/cash-pdf/", cash_statement_pdf, name="cash_statement_pdf"),
    path(
        "teachers/followup/",
        teacher_followup,
        name="teacher_followup",
    ),
    path(
        "teachers/<int:teacher_id>/evaluation/add/",
        teacher_evaluate,
        name="teacher_evaluate",
    ),
]
