import pytest
from django.urls import reverse

from administration.models import Role, SchoolYear, Teacher
from pedagogie.models import Classe, EducationLevel, Teaching
from pedagogie.permissions import TeacherScope

pytestmark = pytest.mark.django_db


@pytest.fixture
def classes(school):
    year = SchoolYear.objects.get(school=school, is_active=True)
    level = EducationLevel.objects.filter(school_type="high_school").order_by("order").first() or EducationLevel.objects.first()
    c1 = Classe.objects.create(school=school, school_year=year, education_level=level, name="Classe A", group="A")
    c2 = Classe.objects.create(school=school, school_year=year, education_level=level, name="Classe B", group="B")
    return c1, c2


def test_teacher_only_sees_his_classes(client, school, login, teacher, classes):
    c1, c2 = classes
    user = login(Role.TEACHER)
    teacher.user = user
    teacher.save()
    Teaching.objects.bulk_create([Teaching(teacher=teacher, classe=c1, subject=None)])  # sans les règles métier de programme
    scope = TeacherScope(user)
    assert scope.class_ids() == {c1.id}
    assert scope.subject_ids(c1.id) is None  # titulaire : toutes les matières
    html = client.get(reverse("term_list")).content.decode()
    assert "Classe A" in html or c1.display_name in html
    assert c2.display_name not in html
    assert "Nouvelle évaluation" not in html


def test_unlinked_teacher_sees_nothing(client, school, login, classes):
    user = login(Role.TEACHER)
    scope = TeacherScope(user)
    assert scope.class_ids() == set()
    assert client.get(reverse("class_results", args=[classes[0].id, 999])).status_code in (403, 404)


def test_studies_director_is_unrestricted(school, make_user):
    user = make_user("de", Role.STUDIES_DIRECTOR)
    assert TeacherScope(user).unrestricted
