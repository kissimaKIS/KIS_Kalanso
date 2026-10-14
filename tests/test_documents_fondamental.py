"""FeedbacksV4 — points 2 et 4 : années passées consultables et documents du fondamental."""
import datetime

import pytest

from administration import documents_fondamental as docs
from administration.models import Role, School, SchoolTypeActivation, SchoolYear
from pedagogie.models import Classe, EducationLevel, Enrollment, Grade, Student, Subject, Term

D = datetime.date


@pytest.fixture
def ecole(db):
    school = School.objects.create(name="Iqra Les Étoiles", code="ILE", school_type="fundamental_1",
                                   city="Koutiala", cap_name="CAP de Koutiala", is_active=True)
    for t in ("fundamental_1", "fundamental_2"):
        SchoolTypeActivation.objects.create(school=school, school_type=t, is_active=True)
    years = []
    for start in (2024, 2025, 2026):
        y = SchoolYear.objects.create(school=school, start_date=D(start, 10, 1), end_date=D(start + 1, 6, 30), is_active=True)
        if start < 2026:
            y.is_active, y.is_closed = False, True
            y.save()
        years.append(y)
    student = Student.objects.create(first_name="Assitan", last_name="Magassouba", sex="F", date_of_birth=D(2010, 11, 21),
                                     place_of_birth="Koutiala", matricule="03", father_name="Moussa Magassouba",
                                     mother_name="Djénéba Traoré")
    l5 = EducationLevel.objects.get(code="F1-5")
    l6 = EducationLevel.objects.get(code="F1-6")
    enrollments = []
    for year, level in zip(years, (l5, l5, l6)):  # la 5e année est doublée
        classe = Classe(school=school, school_year=year, education_level=level, group="A", name="")
        classe.save()
        enrollments.append(Enrollment.objects.create(student=student, classe=classe, school_year=year,
                                                     enrollment_date=year.start_date))
    subject = Subject.objects.create(code="TST-MATH", name="Maths test")
    past = enrollments[1]
    for order, notes in enumerate(((6, 8), (7, 9)), 1):
        term = Term.objects.create(school_year=past.school_year, name=f"{order}ère Période" if order == 1 else f"{order}ème Période", order=order)
        Grade.objects.create(enrollment=past, subject=subject, term=term, composition=notes[0])
    return {"school": school, "years": years, "student": student, "enrollments": enrollments}


def test_fiche_data_follows_the_whole_course(ecole):
    data = docs.fiche_data(ecole["student"], ecole["school"])
    assert set(data.first_cycle) == {"F1-5", "F1-6"}
    assert data.first_cycle["F1-5"] == ecole["enrollments"][1]  # dernière année suivie du niveau
    assert data.doubled == ["5ème année"]
    assert data.recruitment_date == D(2024, 10, 1)


def test_releve_uses_term_averages_of_the_requested_year(ecole):
    data = docs.releve_data(ecole["enrollments"][1])
    assert [v for _, v, _ in data.rows] == [6.0, 7.0]
    assert data.total == 13.0 and data.moyenne == 6.5 and data.scale == 10 and data.total_max == 20


def test_releve_leaves_missing_terms_blank(ecole):
    data = docs.releve_data(ecole["enrollments"][2])  # année en cours, aucune période saisie
    assert data.rows == [] and data.total is None and data.moyenne is None


def test_transfert_for_a_closed_year(ecole):
    data = docs.transfert_data(ecole["enrollments"][1])
    assert data.since == D(2024, 10, 1)
    assert data.until == D(2026, 6, 30)
    assert data.years == 2
    assert data.doubled == ["5ème année"]
    assert data.work  # appréciation calculée sur la moyenne de l'année


def test_transfert_end_date_left_blank_for_current_year(ecole):
    assert docs.transfert_data(ecole["enrollments"][2]).until is None


@pytest.mark.parametrize("url", [
    "/students/{student}/fiche-scolaire/",
    "/enrollments/{past}/releve-notes/",
    "/enrollments/{past}/certificat-transfert/",
    "/enrollments/{past}/certificat-frequentation/",
])
def test_documents_print_for_past_years(client, login, ecole, url):
    login(Role.SECRETARY)
    response = client.get(url.format(student=ecole["student"].id, past=ecole["enrollments"][0].id))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_frequentation_is_in_past_tense_for_a_closed_year(ecole):
    from administration.certificat_pdf import frequentation_sentence
    past = frequentation_sentence(ecole["enrollments"][0])
    current = frequentation_sentence(ecole["enrollments"][2])
    assert "a fréquenté" in past and "2024-2025" in past
    assert "fréquente assidûment" in current


def test_student_list_can_show_a_past_year(client, login, ecole):
    login(Role.SECRETARY)
    other = Student.objects.create(first_name="Seulement", last_name="EnCours")
    Enrollment.objects.create(student=other, classe=ecole["enrollments"][2].classe, school_year=ecole["years"][2])
    html = client.get(f"/students/?annee={ecole['years'][0].id}").content.decode()
    assert "Assitan" in html and "EnCours" not in html
    assert "2024-2025" in html
    html = client.get("/students/?annee=all&q=Assitan").content.decode()
    assert html.count("Magassouba") >= 3  # une ligne par année


def test_student_detail_offers_documents_for_every_year(client, login, ecole):
    login(Role.SECRETARY)
    html = client.get(f"/students/{ecole['student'].id}/").content.decode()
    for e in ecole["enrollments"]:
        assert f"/enrollments/{e.id}/certificat-frequentation/" in html
        assert f"/enrollments/{e.id}/releve-notes/" in html
        assert f"/enrollments/{e.id}/certificat-transfert/" in html
    assert f"/students/{ecole['student'].id}/fiche-scolaire/" in html


def test_teacher_cannot_print_documents(client, login, ecole):
    login(Role.TEACHER)
    response = client.get(f"/enrollments/{ecole['enrollments'][0].id}/certificat-transfert/")
    assert response.status_code != 200 or response["Content-Type"] != "application/pdf"
