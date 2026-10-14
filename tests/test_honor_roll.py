"""Tableau d'honneur du tableau de bord : mêmes moyennes que le bulletin."""
import pytest

from administration.models import HonorRollRule, Role, SchoolYear
from pedagogie.models import BulletinItem, Classe, EducationLevel, Enrollment, Grade, Student, Term
from pedagogie.services.class_results import ClassTermResults


@pytest.fixture
def lycee(school):
    year = SchoolYear.objects.get(school=school)
    year.validate_catalog()
    classe = Classe(school=school, school_year=year, education_level=EducationLevel.objects.get(code="LYC-10"), group="A", name="")
    classe.save()
    links = list(classe.applicable_subject_links().filter(subject__is_active=True)[:2])
    for n, link in enumerate(links, 1):
        BulletinItem.objects.create(classe=classe, subject=link.subject, order=n, coefficient=link.coefficient or 1, max_score=20)
    term = Term.objects.create(school_year=year, name="Période 1", order=1)
    marks = {"Assitan": (20, 20), "Gomba": (15, 16), "Ben": (11, 12)}
    enrollments = {}
    for name, (a, b) in marks.items():
        e = Enrollment.objects.create(student=Student.objects.create(first_name=name, last_name="X"), classe=classe, school_year=year)
        for link in links:
            # Notes saisies dans « Notes du bulletin » (sans évaluation).
            Grade.objects.create(enrollment=e, subject=link.subject, term=term, class_average=a, composition=b)
        enrollments[name] = e
    HonorRollRule.objects.create(school=school, school_type="high_school", scale=20, threshold=14)
    return {"classe": classe, "term": term, "enrollments": enrollments}


def test_bulletin_grades_feed_the_honor_roll(client, login, lycee):
    login(Role.ADMIN)
    html = client.get("/dashboard/").content.decode()
    assert "Assitan X" in html and "Gomba X" in html
    assert "Ben X" not in html
    assert "Aucun élève n'atteint" not in html
    # Même moyenne que sur le bulletin imprimé.
    results = ClassTermResults(lycee["classe"], lycee["term"])
    expected = f"{float(results.average(lycee['enrollments']['Gomba'].id)):.2f}".replace(".", ",")
    assert expected + "/20" in html


def test_missing_threshold_is_explained(client, login, lycee):
    HonorRollRule.objects.all().delete()
    login(Role.ADMIN)
    html = client.get("/dashboard/").content.decode()
    assert "Seuil du tableau d'honneur non configuré pour : Lycée" in html


def test_no_grades_message(client, login, school):
    login(Role.ADMIN)
    assert "Aucune note de bulletin" in client.get("/dashboard/").content.decode()
