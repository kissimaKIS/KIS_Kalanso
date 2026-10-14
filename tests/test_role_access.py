import pytest
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from administration.models import Role
from administration.permissions.access import (
    ALL_PERMISSIONS, BUDGET_MANAGE, FINANCE_MANAGE, PEDAGOGY_MANAGE, ROLE_PERMISSIONS,
    role_label, user_permissions,
)
from administration.permissions.url_rules import PUBLIC_URLS, URL_PERMISSIONS

pytestmark = pytest.mark.django_db


def _url_names(resolver=None, namespace=None):
    resolver = resolver or get_resolver()
    for pattern in resolver.url_patterns:
        if isinstance(pattern, URLResolver):
            if pattern.namespace == "admin":
                continue
            yield from _url_names(pattern, pattern.namespace)
        elif isinstance(pattern, URLPattern) and pattern.name:
            yield pattern.name


def test_every_url_has_a_rule():
    missing = sorted(set(_url_names()) - set(URL_PERMISSIONS) - PUBLIC_URLS)
    assert missing == []


def test_role_matrix_matches_v3_feedback():
    for role in (Role.ADMIN, Role.PROMOTER, Role.MANAGER):
        assert ROLE_PERMISSIONS[role] == ALL_PERMISSIONS
    assert ROLE_PERMISSIONS[Role.DIRECTOR] == ALL_PERMISSIONS - {BUDGET_MANAGE}
    accountant = ROLE_PERMISSIONS[Role.ACCOUNTANT]
    assert FINANCE_MANAGE in accountant and BUDGET_MANAGE not in accountant
    assert PEDAGOGY_MANAGE not in accountant
    studies = ROLE_PERMISSIONS[Role.STUDIES_DIRECTOR]
    assert PEDAGOGY_MANAGE in studies and "students.manage" in studies
    assert not studies & {FINANCE_MANAGE, "finance.collect", BUDGET_MANAGE}
    teacher = ROLE_PERMISSIONS[Role.TEACHER]
    assert not any(p.startswith(("finance", "budget", "salaries")) for p in teacher)
    assert ROLE_PERMISSIONS[Role.STUDENT] == frozenset()
    assert ROLE_PERMISSIONS[Role.PARENT] == frozenset()


def test_accountant_is_not_administrator(client, school, login):
    user = login(Role.ACCOUNTANT)
    assert role_label(user) == "Comptable"
    response = client.get(reverse("dashboard"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "Comptable" in html
    assert "Administrateur" not in html
    assert "Nouvelle inscription" not in html
    assert "Encaissé" in html
    assert "Pédagogie" not in html  # menu masqué
    assert client.get(reverse("budget_list")).status_code == 403
    assert client.get(reverse("user_list")).status_code == 403
    assert client.get(reverse("enrollment_create")).status_code == 403
    assert client.get(reverse("term_list")).status_code == 403
    assert client.get(reverse("fee_type_list")).status_code == 200
    assert client.get(reverse("payment_list")).status_code == 200


def test_director_has_everything_but_budget(client, school, login):
    login(Role.DIRECTOR)
    assert client.get(reverse("budget_list")).status_code == 403
    assert client.get(reverse("user_list")).status_code == 200
    assert client.get(reverse("fee_type_list")).status_code == 200
    html = client.get(reverse("fee_type_list")).content.decode()
    assert "Budget" not in html


@pytest.mark.parametrize("role", [Role.ADMIN, Role.PROMOTER, Role.MANAGER])
def test_full_roles_open_budget(client, school, login, role):
    login(role)
    assert client.get(reverse("budget_list")).status_code == 200
    assert client.get(reverse("dashboard")).status_code == 200


def test_studies_director_scope(client, school, login):
    login(Role.STUDIES_DIRECTOR)
    assert client.get(reverse("term_list")).status_code == 200
    assert client.get(reverse("enrollment_create")).status_code == 200
    assert client.get(reverse("fee_type_list")).status_code == 403
    assert client.get(reverse("payment_list")).status_code == 403
    html = client.get(reverse("dashboard")).content.decode()
    assert "Encaissé" not in html and "Reste à recouvrer" not in html


def test_teacher_dashboard_has_no_finance(client, school, login, teacher):
    user = login(Role.TEACHER)
    teacher.user = user
    teacher.save()
    response = client.get(reverse("dashboard"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "Mes affectations" in html
    assert "Encaissé" not in html and "Élèves" not in html.split("Mes affectations")[0].split("kis-dashboard-header")[-1]
    assert client.get(reverse("payment_list")).status_code == 403
    assert client.get(reverse("teacher_list")).status_code == 403
    assert client.get(reverse("evaluation_create")).status_code == 403
    assert client.get(reverse("teaching_list")).status_code == 200


@pytest.mark.parametrize("role", [Role.STUDENT, Role.PARENT])
def test_student_and_parent_have_no_space(client, school, login, role):
    login(role)
    response = client.get(reverse("startup"))
    assert response.status_code == 302 and response.url == reverse("access_denied")
    assert client.get(reverse("access_denied")).status_code == 403
    assert client.get(reverse("dashboard")).status_code == 403


def test_superuser_without_roles_keeps_full_access(client, school, login):
    user = login(superuser=True, username="root")
    assert user_permissions(user) == ALL_PERMISSIONS
    assert client.get(reverse("budget_list")).status_code == 200
    assert "Administrateur" in client.get(reverse("dashboard")).content.decode()


def test_ajax_denied_returns_modal_snippet(client, school, login):
    login(Role.SECRETARY)
    response = client.get(reverse("user_create"), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    assert response.status_code == 403
    assert "<html" not in response.content.decode()
