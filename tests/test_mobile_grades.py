"""Saisie mobile des notes (lycée / centre) : paquet JSON → téléphone → fichier de notes → Kalanso."""
import json

import pytest

from administration.models import Role, SchoolYear, Teacher
from pedagogie import mobile_grades as mg
from pedagogie.models import (BulletinItem, Classe, EducationLevel, Enrollment, Grade, MobileGradeSubmission,
                              Student, Teaching, Term)


@pytest.fixture
def setup(school, teacher):
    year = SchoolYear.objects.get(school=school)
    year.validate_catalog()
    classe = Classe(school=school, school_year=year, education_level=EducationLevel.objects.get(code="LYC-10"), group="A", name="")
    classe.save()
    subjects = [link.subject for link in classe.applicable_subject_links().filter(subject__is_active=True)[:2]]
    for n, subject in enumerate(subjects, 1):
        BulletinItem.objects.create(classe=classe, subject=subject, order=n, coefficient=1, max_score=20)
    Teaching.objects.create(teacher=teacher, classe=classe, subject=subjects[0])
    term = Term.objects.create(school_year=year, name="Trimestre 1", order=1)
    enrollments = []
    for i, (first, last) in enumerate([("Awa", "Coulibaly"), ("Moussa", "Diallo"), ("Fanta", "Keita")]):
        student = Student.objects.create(first_name=first, last_name=last, matricule=f"L{i}")
        enrollments.append(Enrollment.objects.create(student=student, classe=classe, school_year=year))
    return {"year": year, "classe": classe, "subject": subjects[0], "other_subject": subjects[1], "term": term,
            "teacher": teacher, "enrollments": enrollments}


def phone_file(package, grades_by_enrollment, sheet_index=0):
    """Ce que renverra l'application mobile."""
    content = package.content
    sheet = content["sheets"][sheet_index]
    return json.dumps({
        "format": mg.NOTES_FORMAT, "version": 1,
        "package_id": content["package_id"], "package_signature": content["package_signature"],
        "submitted_at": "2026-11-20T10:00:00",
        "sheets": [{"sheet_id": sheet["sheet_id"], "grades": [
            {"enrollment_id": eid, "class_average": a, "composition": b} for eid, (a, b) in grades_by_enrollment.items()
        ]}],
    }).encode()


def test_package_lists_the_teacher_sheet_with_students_and_current_grades(setup):
    e0 = setup["enrollments"][0]
    Grade.objects.create(enrollment=e0, subject=setup["subject"], term=setup["term"], class_average=11, composition=12)
    package, warnings = mg.build_package(setup["teacher"], setup["term"])
    assert package.content["format"] == mg.PACKAGE_FORMAT
    assert len(package.content["sheets"]) == 1  # seulement sa matière
    sheet = package.content["sheets"][0]
    assert sheet["subject"]["id"] == setup["subject"].id and sheet["scale"] == 20
    first = next(s for s in sheet["students"] if s["enrollment_id"] == e0.id)
    assert (first["class_average"], first["composition"]) == (11, 12)
    assert len(sheet["students"]) == 3


def test_unconfigured_bulletins_are_left_out(setup, school):
    other = Classe(school=school, school_year=setup["year"], education_level=EducationLevel.objects.get(code="LYC-10"), group="B", name="")
    other.save()
    Teaching.objects.create(teacher=setup["teacher"], classe=other, subject=setup["subject"])
    sheets, warnings = mg.teacher_sheets(setup["teacher"], setup["term"])
    assert [s.classe for s in sheets] == [setup["classe"]]
    assert any("bulletin non paramétré" in w for w in warnings)


def test_round_trip_records_grades_after_validation(setup):
    package, _ = mg.build_package(setup["teacher"], setup["term"])
    e = setup["enrollments"]
    raw = phone_file(package, {e[0].id: (12, 14), e[1].id: ("9,5", "11"), e[2].id: (None, None)})
    submission = mg.read_submission(raw, "notes.json")
    report = mg.analyse(submission)
    assert report.to_apply == 2 and report.line_errors == 0
    assert not Grade.objects.exists()  # rien avant validation
    assert mg.apply(submission) == 2
    grade = Grade.objects.get(enrollment=e[1], subject=setup["subject"], term=setup["term"])
    assert (grade.class_average, grade.composition) == (9.5, 11)
    submission.refresh_from_db()
    assert submission.status == MobileGradeSubmission.Status.APPLIED and submission.applied_count == 2
    with pytest.raises(mg.MobileImportError):
        mg.apply(submission)


def test_changed_same_and_empty_lines(setup):
    e = setup["enrollments"]
    Grade.objects.create(enrollment=e[0], subject=setup["subject"], term=setup["term"], class_average=10, composition=10)
    Grade.objects.create(enrollment=e[1], subject=setup["subject"], term=setup["term"], class_average=8, composition=8)
    Grade.objects.create(enrollment=e[2], subject=setup["subject"], term=setup["term"], class_average=7, composition=7)
    package, _ = mg.build_package(setup["teacher"], setup["term"])
    submission = mg.read_submission(phone_file(package, {e[0].id: (10, 10), e[1].id: (8, 15), e[2].id: ("", "")}))
    statuses = {r.enrollment.id: r.status for r in mg.analyse(submission).sheets[0].rows}
    assert statuses == {e[0].id: "same", e[1].id: "changed", e[2].id: "empty"}
    mg.apply(submission)
    assert Grade.objects.get(enrollment=e[2]).composition == 7  # une ligne vide n'efface rien


def test_invalid_lines_are_refused_but_valid_ones_kept(setup):
    package, _ = mg.build_package(setup["teacher"], setup["term"])
    e = setup["enrollments"]
    intruder = Enrollment.objects.create(student=Student.objects.create(first_name="X", last_name="Y"),
                                         classe=setup["classe"], school_year=setup["year"])
    raw = phone_file(package, {e[0].id: (12, None), e[1].id: (25, 10), e[2].id: (13, 13), intruder.id: (10, 10)})
    report = mg.analyse(mg.read_submission(raw))
    rows = report.sheets[0].rows
    assert [r.status for r in rows] == ["error", "error", "new", "error"]
    assert "ensemble" in rows[0].message and "entre 0 et 20" in rows[1].message
    assert report.to_apply == 1


@pytest.mark.parametrize("change, message", [
    (lambda d: d.update(package_signature="faux"), "Signature"),
    (lambda d: d.update(format="autre"), "pas un fichier de notes"),
    (lambda d: d.update(format=mg.PACKAGE_FORMAT), "paquet de saisie"),
    (lambda d: d.update(version=99), "Version"),
])
def test_bad_files_are_rejected(setup, change, message):
    package, _ = mg.build_package(setup["teacher"], setup["term"])
    data = json.loads(phone_file(package, {}))
    change(data)
    with pytest.raises(mg.MobileImportError, match=message):
        mg.read_submission(json.dumps(data).encode())
    with pytest.raises(mg.MobileImportError):
        mg.read_submission(b"pas du json")


def test_sheet_not_in_package_or_teacher_unassigned(setup):
    package, _ = mg.build_package(setup["teacher"], setup["term"])
    data = json.loads(phone_file(package, {setup["enrollments"][0].id: (10, 10)}))
    data["sheets"].append({"sheet_id": f"{setup['classe'].id}-{setup['other_subject'].id}", "grades": []})
    submission = mg.read_submission(json.dumps(data).encode())
    Teaching.objects.filter(teacher=setup["teacher"]).delete()
    report = mg.analyse(submission)
    assert "plus affecté" in report.sheets[0].error
    assert "absente du paquet" in report.sheets[1].error
    assert report.to_apply == 0


def test_closed_year_blocks_import(setup):
    package, _ = mg.build_package(setup["teacher"], setup["term"])
    submission = mg.read_submission(phone_file(package, {setup["enrollments"][0].id: (10, 10)}))
    SchoolYear.objects.filter(pk=setup["year"].pk).update(is_active=False, is_closed=True)
    submission.package.term.school_year.refresh_from_db()
    assert mg.analyse(MobileGradeSubmission.objects.get(pk=submission.pk)).errors
    with pytest.raises(mg.MobileImportError):
        mg.apply(submission)


def test_pages_full_flow(client, login, setup):
    login(Role.STUDIES_DIRECTOR)
    html = client.get("/pedagogie/saisie-mobile/").content.decode()
    assert setup["teacher"].full_name in html
    response = client.post("/pedagogie/saisie-mobile/paquet/", {"teacher": setup["teacher"].id, "term": setup["term"].id})
    assert response["Content-Type"].startswith("application/json")
    assert "attachment" in response["Content-Disposition"]
    package = json.loads(response.content)
    from django.core.files.uploadedfile import SimpleUploadedFile
    from pedagogie.models import MobileGradePackage
    raw = phone_file(MobileGradePackage.objects.get(uid=package["package_id"]), {setup["enrollments"][0].id: (14, 15)})
    response = client.post("/pedagogie/saisie-mobile/charger/", {"notes": SimpleUploadedFile("notes.json", raw)})
    submission = MobileGradeSubmission.objects.get()
    assert response.url.endswith(f"/depots/{submission.id}/")
    assert "Nouvelle" in client.get(response.url).content.decode()
    client.post(f"/pedagogie/saisie-mobile/depots/{submission.id}/valider/")
    assert Grade.objects.get().composition == 15


@pytest.mark.parametrize("role", [Role.TEACHER, Role.ACCOUNTANT, Role.SECRETARY])
def test_other_roles_cannot_load_notes(client, login, setup, role):
    login(role)
    response = client.get("/pedagogie/saisie-mobile/")
    assert response.status_code in (302, 403)
