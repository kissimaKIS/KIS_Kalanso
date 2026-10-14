"""Imports Excel : pas de doublon à la réimportation, pas de mélange élèves / personnel / budget,
et un message clair dans tous les cas."""
from io import BytesIO

import pandas as pd
import pytest
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile

from administration.models import OtherPersonnel, Role, SchoolYear, Teacher
from pedagogie.models import Classe, EducationLevel, Enrollment, Student
from pilotage.models import BudgetEntry


def xlsx(rows, name="fichier.xlsx"):
    buffer = BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def post(client, url, upload):
    response = client.post(url, {"file": upload}, follow=True)
    return " ".join(str(m) for m in get_messages(response.wsgi_request)) or response.content.decode()


BUDGET = [
    {"Date": "05/10/2026", "Libellé": "Inscriptions", "Catégorie": "Scolarité", "Type": "Recette", "Montant": 150000},
    {"Date": "06/10/2026", "Libellé": "Craies", "Catégorie": "Fournitures", "Type": "Dépense", "Montant": 5000},
    {"Date": "06/10/2026", "Libellé": "Craies", "Catégorie": "Fournitures", "Type": "Dépense", "Montant": 5000},
]
STUDENTS = [
    {"Prénom": "Awa", "Nom": "Coulibaly", "Sexe": "F", "DateNaissance": "12/03/2010"},
    {"Prénom": "Moussa", "Nom": "Diallo", "Sexe": "M"},
    {"Prénom": "Fanta", "Nom": "Keita", "Sexe": "F", "Matricule": "E-003"},
]
TEACHERS = [{"Matricule": "T-10", "Prénom": "Sékou", "Nom": "Traoré", "Statut": "Permanent", "Spécialité": "Maths"}]
PERSONNEL = [{"Matricule": "P-1", "Prénom": "Ami", "Nom": "Sow", "Fonction": "Gardien"}]


@pytest.fixture
def classe(school):
    year = SchoolYear.objects.get(school=school)
    year.validate_catalog()
    c = Classe(school=school, school_year=year, education_level=EducationLevel.objects.get(code="LYC-10"), group="A", name="")
    c.save()
    return c


# ----------------------------------------------------------------- budget

def test_budget_reimport_does_not_duplicate(client, login, school):
    login(Role.ADMIN)
    msg = post(client, "/budget/import/", xlsx(BUDGET))
    assert BudgetEntry.objects.count() == 3  # deux « Craies » identiques dans le fichier : gardées
    assert "3 opération(s) importée(s)" in msg
    msg = post(client, "/budget/import/", xlsx(BUDGET))
    assert BudgetEntry.objects.count() == 3
    assert "déjà été importé" in msg


def test_budget_file_extended_later_only_adds_new_lines(client, login, school):
    login(Role.ADMIN)
    post(client, "/budget/import/", xlsx(BUDGET))
    more = BUDGET + [{"Date": "07/10/2026", "Libellé": "Électricité", "Catégorie": "Charges", "Type": "Dépense", "Montant": 20000}]
    msg = post(client, "/budget/import/", xlsx(more))
    assert BudgetEntry.objects.count() == 4
    assert "1 opération(s) importée(s)" in msg and "3 déjà présente(s)" in msg


def test_budget_without_dates_is_not_duplicated_another_day(client, login, school):
    login(Role.ADMIN)
    rows = [{"Libellé": "Don", "Type": "Recette", "Montant": 1000}]
    post(client, "/budget/import/", xlsx(rows))
    BudgetEntry.objects.update(date="2026-01-01")  # importé « un autre jour »
    post(client, "/budget/import/", xlsx(rows))
    assert BudgetEntry.objects.count() == 1


def test_budget_refuses_a_student_list(client, login, school):
    login(Role.ADMIN)
    msg = post(client, "/budget/import/", xlsx(STUDENTS))
    assert BudgetEntry.objects.count() == 0
    assert "ressemble à une liste d'élèves" in msg and "budget" in msg


# ----------------------------------------------------------------- élèves

def test_student_reimport_does_not_duplicate_even_without_matricule(client, login, classe):
    login(Role.ADMIN)
    url = f"/classes/{classe.id}/students/import/"
    msg = post(client, url, xlsx(STUDENTS))
    assert Student.objects.count() == 3 and Enrollment.objects.count() == 3
    assert "3 élève(s) inscrit(s)" in msg
    msg = post(client, url, xlsx(STUDENTS))
    assert Student.objects.count() == 3 and Enrollment.objects.count() == 3
    assert "déjà été importé" in msg


def test_student_already_in_another_class_is_reported(client, login, classe, school):
    login(Role.ADMIN)
    other = Classe(school=school, school_year=classe.school_year, education_level=classe.education_level, group="B", name="")
    other.save()
    post(client, f"/classes/{classe.id}/students/import/", xlsx(STUDENTS))
    msg = post(client, f"/classes/{other.id}/students/import/", xlsx(STUDENTS))
    assert Enrollment.objects.count() == 3
    assert "autre classe" in msg and classe.display_name in msg


def test_same_student_twice_in_file(client, login, classe):
    login(Role.ADMIN)
    msg = post(client, f"/classes/{classe.id}/students/import/", xlsx(STUDENTS[:1] * 2))
    assert Student.objects.count() == 1
    assert "deux fois" in msg


@pytest.mark.parametrize("rows, expected", [(TEACHERS, "liste d'enseignants"), (PERSONNEL, "personnel non enseignant"), (BUDGET, "budget")])
def test_students_refuse_other_files(client, login, classe, rows, expected):
    login(Role.ADMIN)
    msg = post(client, f"/classes/{classe.id}/students/import/", xlsx(rows))
    assert Student.objects.count() == 0
    assert "Import refusé" in msg and expected in msg


def test_students_refuse_minimal_staff_file_by_matricules(client, login, classe, teacher):
    login(Role.ADMIN)
    msg = post(client, f"/classes/{classe.id}/students/import/", xlsx([{"Matricule": teacher.employee_number, "Prénom": "Awa", "Nom": "Diarra"}]))
    assert Student.objects.count() == 0 and "liste du personnel" in msg


# ----------------------------------------------------------------- personnel

@pytest.mark.parametrize("url, model, rows, expected", [
    ("/teachers/import/", Teacher, STUDENTS, "liste d'élèves"),
    ("/teachers/import/", Teacher, PERSONNEL, "personnel non enseignant"),
    ("/other-personnel/import/", OtherPersonnel, STUDENTS, "liste d'élèves"),
    ("/other-personnel/import/", OtherPersonnel, TEACHERS, "liste d'enseignants"),
    ("/other-personnel/import/", OtherPersonnel, BUDGET, "budget"),
])
def test_staff_imports_refuse_other_files(client, login, school, url, model, rows, expected):
    login(Role.ADMIN)
    before = model.objects.count()
    msg = post(client, url, xlsx(rows))
    assert model.objects.count() == before
    assert "Import refusé" in msg and expected in msg


def test_teachers_refuse_minimal_student_file_by_matricules(client, login, school):
    login(Role.ADMIN)
    Student.objects.create(first_name="Awa", last_name="Ba", matricule="E-1")
    msg = post(client, "/teachers/import/", xlsx([{"Matricule": "E-1", "Prénom": "Awa", "Nom": "Ba"}]))
    assert not Teacher.objects.filter(employee_number="E-1").exists()
    assert "liste d'élèves" in msg


def test_teacher_reimport_updates_without_duplicate(client, login, school):
    login(Role.ADMIN)
    post(client, "/teachers/import/", xlsx(TEACHERS))
    msg = post(client, "/teachers/import/", xlsx(TEACHERS))
    assert Teacher.objects.filter(employee_number="T-10").count() == 1
    assert "déjà existant" in msg


def test_headers_are_matched_without_accents_or_case(client, login, school):
    login(Role.ADMIN)
    post(client, "/other-personnel/import/", xlsx([{"MATRICULE": "P-9", "prenom": "Ali", "NOM": "Ba", "fonction": "Comptable"}]))
    assert OtherPersonnel.objects.filter(employee_number="P-9", first_name="Ali").exists()


# ----------------------------------------------------------------- fichiers illisibles

def test_clear_messages_for_unreadable_or_empty_files(client, login, school):
    login(Role.ADMIN)
    msg = post(client, "/budget/import/", SimpleUploadedFile("notes.pdf", b"%PDF-1.4"))
    assert "n'est pas un fichier Excel" in msg
    msg = post(client, "/budget/import/", SimpleUploadedFile("faux.xlsx", b"pas un excel"))
    assert "n'a pas pu être lu" in msg
    msg = post(client, "/budget/import/", xlsx([], name="vide.xlsx"))
    assert "aucune ligne" in msg
    msg = post(client, "/teachers/import/", xlsx([{"Prénom": "A", "Nom": "B"}]))
    assert "Colonnes obligatoires manquantes : Matricule" in msg
