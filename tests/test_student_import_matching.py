"""Import élèves (07/10) : un fichier incomplet puis complété ne doit plus créer de doublons."""
import datetime
from io import BytesIO

import pandas as pd
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from administration.models import Role, SchoolYear
from pedagogie.models import Classe, EducationLevel, Enrollment, Student


def xlsx(rows):
    buf = BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    return SimpleUploadedFile("eleves.xlsx", buf.getvalue())


@pytest.fixture(autouse=True)
def _tmp(settings, tmp_path):
    settings.KIS_DATA_DIR = tmp_path


@pytest.fixture
def classe(school):
    year = SchoolYear.objects.get(school=school)
    year.validate_catalog()
    c = Classe(school=school, school_year=year, education_level=EducationLevel.objects.get(code="LYC-10"), group="A", name="")
    c.save()
    return c


FIRST = [  # fichier incomplet
    {"Prénom": "Moussa Makan", "Nom": "DEMBELE", "Père": "Makan Dembélé", "TelPère": "73167778"},
    {"Prénom": "Almamy Kounta", "Nom": "TRAORE", "Père": "Kounta Traoré", "TelPère": "73242967"},
    {"Prénom": "Aminata", "Nom": "CISSOUMA", "TelPère": "72808025"},
]
SECOND = [  # même fichier complété
    {"Matricule": "48", "Prénom": "Moussa Makan", "Nom": "DEMBELE", "DateNaissance": "29/03/2017", "Père": "Makan Dembélé", "TelPère": "73167778"},
    {"Matricule": "49", "Prénom": "Alimamy Kounta", "Nom": "TRAORE", "DateNaissance": "08/08/2017", "Père": "Kounta Traoré", "TelPère": "73242967"},
    {"Matricule": "34", "Prénom": "Aminata", "Nom": "CISSOUMA", "DateNaissance": "14/12/2016", "TelPère": "72808025"},
    {"Matricule": "51", "Prénom": "Souleymane", "Nom": "TRAORE", "DateNaissance": "02/07/2017"},
]


def test_completed_file_completes_existing_records(client, login, classe):
    login(Role.ADMIN)
    url = f"/classes/{classe.id}/students/import/"
    client.post(url, {"file": xlsx(FIRST)})
    assert Student.objects.count() == 3
    r = client.post(url, {"file": xlsx(SECOND)})
    # Alimamy / Almamy : nom écrit autrement → à vérifier, même élève proposé.
    assert r.status_code == 200 and "import_preview" in r.templates[0].name
    rows = {row.name: row for row in r.context["to_review"]}
    assert list(rows) == ["TRAORE Alimamy Kounta"]
    almamy = Student.objects.get(first_name="Almamy Kounta")
    assert rows["TRAORE Alimamy Kounta"].default_choice == str(almamy.pk)
    # Aucun doublon pour les cas sûrs, même avant confirmation : rien n'est encore écrit.
    assert Student.objects.count() == 3
    row = rows["TRAORE Alimamy Kounta"]
    r = client.post(url, {"token": r.context["token"], "confirm": "1", f"choice_{row.index}": str(almamy.pk),
                          f"replace_{row.index}": ["first_name"]})
    assert r.status_code == 302
    assert Student.objects.count() == 4                       # seul Souleymane est nouveau
    moussa = Student.objects.get(first_name="Moussa Makan")
    assert moussa.matricule == "48" and moussa.date_of_birth == datetime.date(2017, 3, 29)
    almamy.refresh_from_db()
    assert almamy.first_name == "Alimamy Kounta" and almamy.matricule == "49"
    assert Enrollment.objects.count() == 4


def test_clear_cases_import_directly(client, login, classe):
    login(Role.ADMIN)
    url = f"/classes/{classe.id}/students/import/"
    client.post(url, {"file": xlsx(FIRST[:1])})
    r = client.post(url, {"file": xlsx(SECOND[:1])}, follow=True)
    assert "complétée" in " ".join(str(m) for m in r.context["messages"])
    assert Student.objects.get().matricule == "48"


def test_different_information_is_never_overwritten_silently(client, login, classe):
    login(Role.ADMIN)
    url = f"/classes/{classe.id}/students/import/"
    client.post(url, {"file": xlsx([{"Prénom": "Awa", "Nom": "Keita", "TelPère": "70000000", "Lieu": "Ségou"}])})
    r = client.post(url, {"file": xlsx([{"Prénom": "Awa", "Nom": "Keita", "TelPère": "70000000", "Lieu": "Bamako"}])})
    row = r.context["to_review"][0]
    assert [d[0] for d in row.differences] == ["place_of_birth"]
    client.post(url, {"token": r.context["token"], "confirm": "1", f"choice_{row.index}": row.default_choice})
    assert Student.objects.get().place_of_birth == "Ségou"   # rien de coché : la fiche reste telle quelle


def test_homonyms_without_common_clue_are_asked(client, login, classe, school):
    login(Role.ADMIN)
    Student.objects.create(first_name="Fatoumata", last_name="Traoré", father_phone="70000001")
    url = f"/classes/{classe.id}/students/import/"
    r = client.post(url, {"file": xlsx([{"Prénom": "Fatoumata", "Nom": "TRAORE", "TelPère": "70000002"}])})
    row = r.context["to_review"][0]
    assert row.default_choice == "new" and len(row.candidates) == 1
    client.post(url, {"token": r.context["token"], "confirm": "1", f"choice_{row.index}": "new"})
    assert Student.objects.filter(first_name="Fatoumata").count() == 2
