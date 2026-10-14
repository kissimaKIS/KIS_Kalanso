"""Formulaire d'affectation : ordre des champs et type proposé par défaut."""
import re

import pytest

from administration.models import Role, SchoolYear, Teacher
from pedagogie.models import Classe, EducationLevel, Teaching


@pytest.fixture
def classe(school):
    year = SchoolYear.objects.get(school=school)
    year.validate_catalog()
    c = Classe(school=school, school_year=year, education_level=EducationLevel.objects.get(code="LYC-10"), group="A", name="")
    c.save()
    return c


@pytest.mark.parametrize("modal", [False, True])
def test_class_comes_before_subject_and_subject_teaching_is_default(client, login, classe, teacher, modal):
    login(Role.ADMIN)
    headers = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"} if modal else {}
    html = client.get("/pedagogie/affectations/add/", **headers).content.decode()
    positions = [html.index(f'id="id_{name}"') for name in ("teacher", "classe", "assignment_type", "subject")]
    assert positions == sorted(positions)
    assert re.search(r'<option value="subject_teaching" selected>', html)
    assert "data-class-subjects" in html


def test_specialist_assignment_saves_subject(client, login, classe, teacher):
    login(Role.ADMIN)
    subject = classe.applicable_subject_links().first().subject
    client.post("/pedagogie/affectations/add/", {"teacher": teacher.id, "classe": classe.id,
                                                 "assignment_type": "subject_teaching", "subject": subject.id})
    assert Teaching.objects.get().subject == subject


@pytest.mark.parametrize("modal", [False, True])
def test_form_data_is_valid_json_for_the_browser(client, login, classe, teacher, modal):
    """Régression : avec |escapejs dans l'attribut, le navigateur recevait des
    \\u0022 au lieu de guillemets, JSON.parse échouait et la matière restait grisée."""
    import html as htmllib
    import json
    login(Role.ADMIN)
    headers = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"} if modal else {}
    page = client.get("/pedagogie/affectations/add/", **headers).content.decode()
    profiles = json.loads(htmllib.unescape(re.search(r'data-teacher-profiles="([^"]*)"', page).group(1)))
    subjects = json.loads(htmllib.unescape(re.search(r'data-class-subjects="([^"]*)"', page).group(1)))
    assert profiles[str(teacher.id)] == "specialiste"
    assert len(subjects[str(classe.id)]) > 0
