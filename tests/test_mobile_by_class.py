"""Saisie mobile : paquet par classe (secrétariat / direction) et Fondamentale 1 (note unique)."""
import datetime
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from administration.models import Role, School, SchoolTypeActivation, SchoolYear, Teacher
from pedagogie import mobile_grades as mg
from pedagogie.models import (BulletinItem, BulletinItemResult, Classe, EducationLevel, Enrollment, Grade,
                              MobileGradePackage, Student, Teaching, Term)

from .test_mobile_grades import setup  # noqa: F401 (fixture)

APP = Path(__file__).resolve().parent.parent / "mobile_app" / "KIS_Kalanso_Notes"


@pytest.fixture
def ecole(db):
    school = School.objects.create(name="École F", code="EF", school_type="fundamental_1", is_active=True)
    SchoolTypeActivation.objects.create(school=school, school_type="fundamental_1", is_active=True)
    year = SchoolYear.objects.create(school=school, start_date=datetime.date(2026, 10, 1), end_date=datetime.date(2027, 6, 30), is_active=True)
    year.validate_catalog()
    classe = Classe(school=school, school_year=year, education_level=EducationLevel.objects.get(code="F1-3"), group="A", name="")
    classe.save()
    subjects = [link.subject for link in classe.applicable_subject_links().filter(subject__is_active=True)[:2]]
    for n, subject in enumerate(subjects, 1):
        BulletinItem.objects.create(classe=classe, subject=subject, order=n, coefficient=1, max_score=10)
    conduite = BulletinItem.objects.create(classe=classe, label="Conduite", order=99, coefficient=1, max_score=10)
    term = Term.objects.create(school_year=year, name="1ère période", order=1)
    enrollments = [Enrollment.objects.create(student=Student.objects.create(first_name=f"E{i}", last_name="Ba"), classe=classe, school_year=year)
                   for i in range(3)]
    return {"classe": classe, "subjects": subjects, "conduite": conduite, "term": term, "enrollments": enrollments, "year": year}


def notes_file(package, values):
    """values : {sheet_id: {enrollment_id: dict de champs}}"""
    c = package.content
    return json.dumps({"format": mg.NOTES_FORMAT, "version": 1, "package_id": c["package_id"],
                       "package_signature": c["package_signature"],
                       "sheets": [{"sheet_id": sid, "grades": [{"enrollment_id": e, **v} for e, v in lines.items()]}
                                  for sid, lines in values.items()]}).encode()


def test_class_package_contains_the_whole_bulletin_in_single_note_mode(ecole):
    package, _ = mg.build_package(None, ecole["term"], classes=[ecole["classe"]])
    assert package.teacher is None and package.holder == ecole["classe"].display_name
    sheets = package.content["sheets"]
    assert len(sheets) == 3  # 2 matières + Conduite
    assert all(s["mode"] == "single" and s["scale"] == 10 for s in sheets)
    assert sheets[0]["fields"] == [{"key": "note", "label": "Note"}]
    assert "note" in sheets[0]["students"][0] and "composition" not in sheets[0]["students"][0]


def test_single_note_round_trip_for_subjects_and_custom_lines(ecole):
    e = ecole["enrollments"]
    Grade.objects.create(enrollment=e[0], subject=ecole["subjects"][0], term=ecole["term"], composition=6)
    package, _ = mg.build_package(None, ecole["term"], classes=[ecole["classe"]], label="Secrétariat")
    sid_subject, _, sid_item = (s["sheet_id"] for s in package.content["sheets"])
    assert package.content["sheets"][0]["students"][0]["note"] == 6.0
    submission = mg.read_submission(notes_file(package, {
        sid_subject: {e[0].id: {"note": 6}, e[1].id: {"note": "7,5"}, e[2].id: {"note": 11}},
        sid_item: {e[0].id: {"note": 9}},
    }))
    report = mg.analyse(submission)
    statuses = [r.status for r in report.sheets[0].rows]
    assert statuses == ["same", "new", "error"]
    assert "entre 0 et 10" in report.sheets[0].rows[2].message
    assert mg.apply(submission) == 2
    grade = Grade.objects.get(enrollment=e[1], subject=ecole["subjects"][0])
    assert (grade.composition, grade.class_average) == (7.5, None)
    result = BulletinItemResult.objects.get(enrollment=e[0], bulletin_item=ecole["conduite"])
    assert float(result.note) == 9 and result.class_average is None


def test_class_package_does_not_depend_on_teacher_assignments(setup):
    package, _ = mg.build_package(None, setup["term"], classes=[setup["classe"]])
    assert {s["sheet_id"] for s in package.content["sheets"]} == {
        f"{setup['classe'].id}-{setup['subject'].id}", f"{setup['classe'].id}-{setup['other_subject'].id}"}
    assert all(s["mode"] == "ab" for s in package.content["sheets"])
    Teaching.objects.all().delete()
    sid = package.content["sheets"][1]["sheet_id"]
    submission = mg.read_submission(notes_file(package, {sid: {setup["enrollments"][0].id: {"class_average": 10, "composition": 12}}}))
    assert mg.apply(submission) == 1


def test_fundamental_teacher_package(ecole):
    teacher = Teacher.objects.create(employee_number="TF1", first_name="Maître", last_name="Titulaire")
    Teaching.objects.create(teacher=teacher, classe=ecole["classe"], subject=None)
    package, _ = mg.build_package(teacher, ecole["term"])
    assert len(package.content["sheets"]) == 3  # titulaire : tout, Conduite comprise
    assert package.content["label"] == teacher.full_name


def test_class_package_page(client, login, ecole):
    login(Role.STUDIES_DIRECTOR)
    html = client.get("/pedagogie/saisie-mobile/").content.decode()
    assert "Paquet par classe" in html and ecole["classe"].display_name in html
    response = client.post("/pedagogie/saisie-mobile/paquet/", {"term": ecole["term"].id, "classes": [ecole["classe"].id], "label": "Secrétariat"})
    assert response["Content-Type"].startswith("application/json")
    assert "paquet_Secr" in response["Content-Disposition"]
    assert MobileGradePackage.objects.get().label == "Secrétariat"
    response = client.post("/pedagogie/saisie-mobile/paquet/", {"term": ecole["term"].id})
    assert response.status_code == 302  # aucune classe cochée


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js absent")
def test_mobile_logic_round_trip_single_mode(ecole, tmp_path):
    package, _ = mg.build_package(None, ecole["term"], classes=[ecole["classe"]])
    path = tmp_path / "paquet.json"
    path.write_text(mg.package_json(package), encoding="utf-8")
    out = subprocess.run(["node", str(APP / "tests" / "fill_package.js"), str(path)], capture_output=True, text=True, check=True)
    submission = mg.read_submission(out.stdout.encode())
    assert mg.analyse(submission).line_errors == 0
    assert mg.apply(submission) == 9
