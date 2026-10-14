"""Garde-fous de performance : le nombre de requêtes d'une page ne doit pas
croître avec le nombre d'élèves (sinon : lenteur dès quelques centaines)."""
import pytest
from django.urls import reverse

from administration.models import Role
from common.views import bulletins_for
from pedagogie.models import Bulletin, Classe, Enrollment, Grade
from pedagogie.services.class_results import ClassTermResults
from pedagogie.utils import moyenne_generale

from .conftest import build_complex

pytestmark = pytest.mark.django_db


@pytest.fixture
def data(db):
    return build_complex(n_students=48, n_classes=4)


def _round(value):
    return None if value is None else round(float(value), 6)


@pytest.mark.parametrize("school_types", [("fundamental_1",), ("fundamental_2", "high_school")])
def test_grouped_results_match_per_student_computation(db, school_types):
    data = build_complex(n_students=30, n_classes=2, school_types=school_types)
    for classe in data["classes"]:
        results = ClassTermResults(classe, data["term"])
        for enrollment in Enrollment.objects.filter(classe=classe):
            bulletin = Bulletin.objects.create(enrollment=enrollment, term=data["term"])
            assert _round(results.average(enrollment.id)) == _round(moyenne_generale(enrollment, data["term"]))
            assert results.rank(enrollment.id) == bulletin._rang_unitaire()
            old = bulletin._lignes_unitaires()
            new = results.lines(enrollment.id)
            assert [(r["display_name"], _round(r["moyenne"]), r["appreciation"]) for r in old] == \
                   [(r["display_name"], _round(r["moyenne"]), r["appreciation"]) for r in new]


def test_list_pages_have_constant_query_count(client, data, login, django_assert_max_num_queries):
    login(Role.ADMIN)
    classe = data["classes"][0]
    pages = [
        reverse("student_list"), reverse("invoice_list"), reverse("payment_list"),
        reverse("debt_report"), reverse("payment_start"), reverse("attendance_list"),
        reverse("attendance_list") + f"?classe={classe.id}", reverse("teaching_list"),
        reverse("term_list"), reverse("discipline_list"), reverse("dashboard"),
        reverse("budget_list"),
    ]
    for url in pages:
        with django_assert_max_num_queries(40):
            assert client.get(url).status_code == 200, url


def test_class_bulletins_pdf_is_not_quadratic(client, data, login, django_assert_max_num_queries):
    login(Role.ADMIN)
    classe = data["classes"][0]
    n = Enrollment.objects.filter(classe=classe).count()
    # ~2 requêtes d'en-tête par bulletin au maximum, plus un socle fixe.
    with django_assert_max_num_queries(30 + 3 * n):
        response = client.get(reverse("class_bulletins_pdf", args=[classe.id, data["term"].id]))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"


def test_lists_are_paginated(client, db, login):
    build_complex(n_students=120, n_classes=2)
    login(Role.ADMIN)
    html = client.get(reverse("student_list")).content.decode()
    assert "Page 1 / 3" in html
    html = client.get(reverse("student_list") + "?page=3").content.decode()
    assert "Page 3 / 3" in html


def test_bulletin_grade_save_ignores_evaluation_grades(client, data, login):
    """Régression : une note d'évaluation pour la même matière faisait planter
    l'enregistrement des notes du bulletin (MultipleObjectsReturned)."""
    from pedagogie.models import BulletinItem, Evaluation, EvaluationSubject

    login(Role.ADMIN)
    classe = next(c for c in data["classes"] if c.education_level.school_type == "fundamental_1")
    item = BulletinItem.objects.filter(classe=classe, subject__isnull=False).first()
    enrollment = Enrollment.objects.filter(classe=classe).first()
    evaluation = Evaluation.objects.create(classe=classe, term=data["term"], name="Compo", date=data["year"].start_date)
    EvaluationSubject.objects.create(evaluation=evaluation, subject_id=item.subject_id)
    Grade.objects.create(enrollment=enrollment, subject_id=item.subject_id, term=data["term"], evaluation=evaluation, composition=5)
    response = client.post(
        reverse("class_results", args=[classe.id, data["term"].id]),
        {"item_id": item.id, f"composition_{enrollment.id}_{item.subject_id}": "8"},
    )
    assert response.status_code == 302
    assert Grade.objects.get(enrollment=enrollment, subject_id=item.subject_id, term=data["term"], evaluation__isnull=True).composition == 8


def test_bulletins_for_creates_missing_in_bulk(data):
    classe = data["classes"][0]
    enrollments = list(Enrollment.objects.filter(classe=classe))
    bulletins = bulletins_for(enrollments, data["term"])
    assert len(bulletins) == len(enrollments)
    assert Bulletin.objects.filter(term=data["term"]).count() == len(enrollments)
    assert len(bulletins_for(enrollments, data["term"])) == len(enrollments)
