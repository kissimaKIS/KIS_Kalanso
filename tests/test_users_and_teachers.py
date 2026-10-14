import io

import pytest
from django.urls import reverse

from administration.forms.teacher import TeacherForm
from administration.forms.user_form import UserCreateForm
from administration.models import Role, Teacher, User

pytestmark = pytest.mark.django_db


def test_teacher_form_creates_no_user_account(school):
    before = User.objects.count()
    form = TeacherForm(data={
        "employee_number": "E42", "first_name": "Moussa", "last_name": "Keita", "phone": "7600",
        "contract_type": "permanent", "pedagogical_profile": "specialiste", "is_active": "on",
    }, school=school)
    assert form.is_valid(), form.errors
    teacher = form.save()
    assert User.objects.count() == before
    assert teacher.user is None
    assert str(teacher) == "Moussa Keita"


def test_teacher_import_creates_no_user_account(client, school, login):
    import pandas as pd
    login(Role.ADMIN)
    before = User.objects.count()
    buffer = io.BytesIO()
    pd.DataFrame([{"Matricule": "M1", "Prénom": "Fanta", "Nom": "Coulibaly", "Téléphone": "66"}]).to_excel(buffer, index=False)
    buffer.seek(0)
    buffer.name = "ens.xlsx"
    response = client.post(reverse("import_teachers"), {"file": buffer})
    assert response.status_code == 302
    assert Teacher.objects.get(employee_number="M1").full_name == "Fanta Coulibaly"
    assert User.objects.count() == before


def test_director_cannot_grant_promoter_or_budget(school, make_user):
    director = make_user("dir", Role.DIRECTOR)
    form = UserCreateForm(request_user=director)
    offered = {value for value, _ in form.fields["roles"].choices}
    assert Role.PROMOTER not in offered and Role.ADMIN not in offered and Role.MANAGER not in offered
    assert Role.ACCOUNTANT in offered and Role.DIRECTOR in offered
    assert Role.PROF not in offered  # doublon historique masqué
    form = UserCreateForm(data={"username": "x", "password": "motdepasse1", "roles": [Role.PROMOTER]}, request_user=director)
    assert not form.is_valid()


def test_director_cannot_edit_promoter(client, school, login, make_user):
    promoter = make_user("promo", Role.PROMOTER)
    login(Role.DIRECTOR)
    assert client.get(reverse("user_edit", args=[promoter.pk])).status_code == 403


def test_teacher_account_must_be_linked_to_teacher_record(school, make_user, teacher):
    admin = make_user("adm", Role.ADMIN)
    form = UserCreateForm(data={"username": "awa", "password": "motdepasse1", "roles": [Role.TEACHER], "is_active": "on"}, request_user=admin)
    assert not form.is_valid()
    assert "teacher" in form.errors
    form = UserCreateForm(data={"username": "awa", "password": "motdepasse1", "roles": [Role.TEACHER], "teacher": teacher.pk, "is_active": "on"}, request_user=admin)
    assert form.is_valid(), form.errors
    user = form.save()
    teacher.refresh_from_db()
    assert teacher.user == user
