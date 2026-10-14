"""Retours du 08/10 : Retour cohérent, année consultée, fiche élève (contact, recrutement,
matricule automatique, QR), affectations libres, salaires (annulation, bulletin de paie)."""
import datetime
from decimal import Decimal

import pytest

from administration.models import CorrectionLog, Role, SchoolYear, Teacher, TeacherPayment
from finance.models import FeeType, Invoice
from pedagogie.models import Classe, EducationLevel, Enrollment, Student, Teaching


@pytest.fixture
def ctx(school):
    year = SchoolYear.objects.get(school=school)
    year.validate_catalog()
    classe = Classe(school=school, school_year=year, education_level=EducationLevel.objects.get(code="LYC-10"), group="A", name="")
    classe.save()
    FeeType.objects.create(name="Scolarité", category="tuition", school_year=year, amount=Decimal("90000"), is_required=True)
    student = Student.objects.create(first_name="Ousmane", last_name="Cissao", sex="M", father_name="Bakary Cissao",
                                     father_phone="70000001", recruitment_year=2026)
    enrollment = Enrollment.objects.create(student=student, classe=classe, school_year=year)
    return dict(year=year, classe=classe, student=student, enrollment=enrollment, school=school)


# ---------------------------------------------------------------- Retour
def test_back_returns_to_class_after_adjusting_the_student(client, login, ctx):
    login(Role.ADMIN)
    s, c, e = ctx["student"], ctx["classe"], ctx["enrollment"]
    client.get("/classes/")
    client.get(f"/classes/{c.id}/")
    r = client.get(f"/students/{s.id}/")
    assert r.context["kis_back_url"] == f"/classes/{c.id}/"
    r = client.get(f"/finance/enrollments/{e.id}/adjust/")
    assert r.context["kis_back_url"] == f"/students/{s.id}/"
    client.post(f"/finance/enrollments/{e.id}/adjust/", {})  # enregistré → redirection vers la fiche
    r = client.get(f"/students/{s.id}/")
    assert r.context["kis_back_url"] == f"/classes/{c.id}/"   # et non plus la finance ou le formulaire
    r = client.get(f"/classes/{c.id}/")
    assert r.context["kis_back_url"] == "/classes/"
    assert "← Retour" in r.content.decode()
    r = client.get("/classes/")
    assert r.context["kis_back_url"] is None                 # page d'entrée de menu : pas de Retour


def test_back_after_payment_goes_to_student_not_to_payment_form(client, login, ctx):
    login(Role.ADMIN)
    s, e = ctx["student"], ctx["enrollment"]
    inv = Invoice.objects.get(enrollment=e)
    client.get(f"/students/{s.id}/")
    client.get(f"/finance/encaissement/{e.id}/")
    r = client.post(f"/finance/encaissement/{e.id}/", {"invoice": [inv.id], f"amount_{inv.id}": "10000"}, follow=True)
    assert r.context["kis_back_url"] == f"/students/{s.id}/"
    html = r.content.decode()
    assert "Fiche de l&#x27;élève" in html or "Fiche de l'élève" in html
    assert f"/classes/{ctx['classe'].id}/" in html


# ---------------------------------------------------------------- Année consultée
def test_closed_year_can_be_viewed_read_only(client, login, ctx, school):
    old = SchoolYear(school=school, start_date=datetime.date(2025, 10, 1), end_date=datetime.date(2026, 6, 30), is_archive=True)
    old.save()
    SchoolYear.objects.filter(pk=old.pk).update(is_archive=False, is_closed=True, is_active=False)
    old.refresh_from_db()
    from pedagogie.models import SchoolYearLevel
    SchoolYearLevel.objects.get_or_create(school_year=old, education_level=ctx["classe"].education_level, defaults={"is_active": True})
    old_class = Classe.objects.create(school=school, school_year=old, education_level=ctx["classe"].education_level, group="B", name="10e B 2025")
    login(Role.ADMIN)
    assert old_class.display_name not in client.get("/classes/").content.decode()
    client.post("/annee-consultee/", {"year": old.pk, "next": "/classes/"})
    page = client.get("/classes/").content.decode()
    assert "lecture seule" in page and "2025-2026" in page
    assert f"/classes/{old_class.id}/" in page
    # Enregistrer quelque chose est refusé tant qu'on consulte l'année passée.
    r = client.post("/classes/add/", {"education_level": ctx["classe"].education_level.id, "group": "C"}, follow=True)
    assert "rien n&#x27;a été enregistré" in r.content.decode() or "rien n'a été enregistré" in r.content.decode()
    client.post("/annee-consultee/", {"year": "active", "next": "/classes/"})
    assert "lecture seule" not in client.get("/classes/").content.decode()


# ---------------------------------------------------------------- Contact, recrutement, QR
def test_contact_person_replaces_father_on_internal_documents(ctx):
    s = ctx["student"]
    assert s.responsible_name == "Bakary Cissao" and s.responsible_phone == "70000001" and s.responsible_relation == "Père"
    s.contact_name, s.contact_phone, s.contact_relation = "Awa Diarra", "76000000", "Tante"
    s.save()
    assert s.responsible_label == "Awa Diarra (tante)" and s.responsible_phone == "76000000"


def test_receipt_and_family_invoice_show_the_contact(client, login, ctx):
    from io import BytesIO
    from pypdf import PdfReader
    s = ctx["student"]
    s.contact_name, s.contact_phone, s.contact_relation = "Awa Diarra", "76000000", "Tante"
    s.save()
    login(Role.ADMIN)
    pdf = client.get(f"/finance/famille/{ctx['enrollment'].id}/situation/").content
    text = PdfReader(BytesIO(pdf)).pages[0].extract_text()
    assert "Awa Diarra" in text and "76000000" in text


def test_qr_code_contains_identity(ctx):
    from administration.carte_identite_pdf import qr_payload
    s = ctx["student"]; s.matricule = "26LT1M"; s.save()
    payload = qr_payload(ctx["enrollment"], ctx["school"])
    assert payload.split("\n") == ["26LT1M", "Ousmane Cissao", ctx["classe"].display_name, ctx["school"].name, "2026-2027"]


# ---------------------------------------------------------------- Matricule automatique
def test_matricule_format_and_numbering(ctx):
    from administration.services import matricule as mat
    school = ctx["school"]
    assert mat.school_sigle(school) == "LT"
    assert mat.propose(school, 2022, "F") == "22LT1F"
    Student.objects.create(first_name="A", last_name="B", matricule="21LT7M")
    assert mat.propose(school, 2026, "M") == "26LT8M"          # le numéro continue sur toute l'école
    assert mat.propose(school, 2026, None) is None


def test_regeneration_asks_missing_data_then_replaces_all(client, login, ctx):
    from administration.services import matricule as mat
    older = Student.objects.create(first_name="Awa", last_name="Keita", sex="F", recruitment_year=2022, matricule="12")
    missing = Student.objects.create(first_name="Sidi", last_name="Daou")
    login(Role.ADMIN)
    page = client.get("/students/matricules/")
    assert [i["student"] for i in page.context["incomplete"]] == [missing]
    r = client.post("/students/matricules/", {"action": "generate"}, follow=True)
    assert Student.objects.get(pk=older.pk).matricule == "12"   # refusé tant qu'une fiche est incomplète
    client.post("/students/matricules/", {"action": "complete", f"year_{missing.pk}": "2024", f"sex_{missing.pk}": "M"})
    client.post("/students/matricules/", {"action": "generate"})
    values = {s.first_name: s.matricule for s in Student.objects.all()}
    assert values == {"Awa": "22LT1F", "Sidi": "24LT2M", "Ousmane": "26LT3M"}
    assert CorrectionLog.objects.filter(action=CorrectionLog.Action.MATRICULES).exists()


def test_enrollment_proposes_and_secures_the_matricule(client, login, ctx):
    login(Role.ADMIN)
    page = client.get("/enrollments/new/").content.decode()
    assert "id_recruitment_year" in page and "Personne de contact" in page
    Student.objects.create(first_name="X", last_name="Y", matricule="26LT5M")
    r = client.post("/enrollments/new/", {"first_name": "Binta", "last_name": "Sy", "sex": "F", "recruitment_year": "2026",
                                          "matricule": "26LT5F", "classe": ctx["classe"].id, "student_type": "regulier"})
    assert r.status_code == 302
    assert Student.objects.get(first_name="Binta").matricule == "26LT6F"   # n° recalculé à l'enregistrement


# ---------------------------------------------------------------- Affectations libres
def test_generalist_can_be_assigned_anywhere(client, login, ctx, school):
    t = Teacher.objects.create(employee_number="G1", first_name="Awa", last_name="Ba",
                               pedagogical_profile=Teacher.PedagogicalProfile.GENERALISTE)
    login(Role.ADMIN)
    subject = ctx["classe"].applicable_subject_links().first().subject
    client.post("/pedagogie/affectations/add/", {"teacher": t.id, "classe": ctx["classe"].id,
                                                 "assignment_type": "subject_teaching", "subject": subject.id})
    assert Teaching.objects.get(teacher=t).subject == subject      # lycée + matière : accepté


# ---------------------------------------------------------------- Salaires
def test_salary_cancel_and_payslip(client, login, ctx, teacher):
    payments = [TeacherPayment.objects.create(teacher=teacher, school_year=ctx["year"], period=f"Mois {i}", amount=Decimal("75000"))
                for i in range(1, 10)]
    login(Role.ADMIN)
    r = client.get(f"/salaires/enseignants/{payments[0].id}/bulletin/")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    from io import BytesIO
    from pypdf import PdfReader
    text = PdfReader(BytesIO(r.content)).pages[0].extract_text()
    assert text.count("BULLETIN DE SALAIRE") == 2 and "soixante-quinze mille" in text
    r = client.post("/salaires/enseignants/annuler/", {"payment": [p.id for p in payments[1:]], "reason": ""})
    assert TeacherPayment.objects.count() == 9                    # motif obligatoire
    r = client.post("/salaires/enseignants/annuler/", {"payment": [p.id for p in payments[1:]], "reason": "toute l'année saisie par erreur"})
    assert r.status_code == 302 and TeacherPayment.objects.count() == 1
    log = CorrectionLog.objects.get(action=CorrectionLog.Action.SALARY_CANCEL)
    assert log.amount == Decimal("600000") and "Mois 9" in log.description
    client.logout()
    login(Role.ACCOUNTANT, username="compta")
    assert client.get("/salaires/enseignants/annuler/").status_code in (302, 403)
    assert client.get(f"/salaires/enseignants/{payments[0].id}/bulletin/").status_code == 200
