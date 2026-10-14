import pytest
from django.urls import NoReverseMatch, reverse

from administration.models import Role
from administration.permissions.middleware import user_can_open
from administration.permissions.url_rules import URL_PERMISSIONS

pytestmark = pytest.mark.django_db

ROLES = [Role.ADMIN, Role.DIRECTOR, Role.ACCOUNTANT, Role.STUDIES_DIRECTOR, Role.SECRETARY, Role.TEACHER]
SKIP = {"user_toggle", "school_year_create"}  # actions POST / parcours d'assistant


@pytest.mark.parametrize("role", ROLES)
def test_pages_without_arguments_render_or_refuse_cleanly(client, school, login, role):
    user = login(role)
    for name in sorted(URL_PERMISSIONS):
        if name in SKIP:
            continue
        try:
            url = reverse(name)
        except NoReverseMatch:
            continue
        response = client.get(url)
        assert response.status_code < 500, (role, name)
        if not user_can_open(user, name):
            assert response.status_code == 403, (role, name)
