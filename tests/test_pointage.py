"""Pointage par QR code (V8-8) : paquet, relevé hors connexion, synchronisation, badges."""
import datetime
import json
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from administration.models import OtherPersonnel, Role, SchoolYear, Teacher
from pedagogie.models import Classe, EducationLevel, Enrollment, Student
from vie_scolaire.models import Attendance, OtherPersonnelAttendance, PointageConfig, PointageScan, TeacherAttendance
from vie_scolaire.services import pointage as svc


@pytest.fixture
def ctx(school):
    year = SchoolYear.objects.get(school=school)
    year.validate_catalog()
    classe = Classe(school=school, school_year=year, education_level=EducationLevel.objects.get(code="LYC-10"), group="A", name="")
    classe.save()
    ali = Student.objects.create(first_name="Ali", last_name="Diallo", matricule="26LT1M")
    awa = Student.objects.create(first_name="Awa", last_name="Sow")                      # sans matricule
    for s in (ali, awa):
        Enrollment.objects.create(student=s, classe=classe, school_year=year)
    teacher = Teacher.objects.create(employee_number="E01", first_name="Moussa", last_name="Keita")
    guard = OtherPersonnel.objects.create(school=school, employee_number="P07", first_name="Sidi", last_name="Traoré", function="Gardien")
    day = max(year.start_date, min(datetime.date.today(), year.end_date))
    return dict(year=year, classe=classe, ali=ali, awa=awa, teacher=teacher, guard=guard, day=day, school=school)


def export(day, scans, device="tel-1"):
    return {"format": svc.EXPORT_FORMAT, "version": 1, "device_id": device,
            "scans": [{"id": i, "code": code, "kind": kind, "at": f"{day.isoformat()}T{hour}"} for i, code, kind, hour in scans]}


def test_codes_and_package(ctx):
    assert svc.resolve("KIS-ENS-E01") == (PointageScan.Person.TEACHER, ctx["teacher"])
    assert svc.resolve("kis-per-p07") == (PointageScan.Person.STAFF, ctx["guard"])
    assert svc.resolve("26LT1M\nAli Diallo\n10e A\nLycée\n2026-2027") == (PointageScan.Person.STUDENT, ctx["ali"])   # carte d'identité
    assert svc.resolve(f"KIS-ELV-{ctx['awa'].pk}") == (PointageScan.Person.STUDENT, ctx["awa"])
    assert svc.resolve("n'importe quoi")[1] is None
    from administration.carte_identite_pdf import qr_payload
    awa_enrollment = Enrollment.objects.get(student=ctx["awa"])
    assert qr_payload(awa_enrollment, ctx["school"]).splitlines()[0] == f"KIS-ELV-{ctx['awa'].pk}"
    package = svc.build_package(ctx["school"], ["http://192.168.1.20:8000/"])
    codes = {p["code"]: p["type"] for p in package["people"]}
    assert codes == {"KIS-ENS-E01": "teacher", "KIS-PER-P07": "staff", "26LT1M": "student", f"KIS-ELV-{ctx['awa'].pk}": "student"}
    assert package["server"] == {"urls": ["http://192.168.1.20:8000/"], "key": PointageConfig.get().api_key}


def test_offline_scans_fill_attendance(ctx):
    day = ctx["day"]
    PointageConfig.objects.update_or_create(id=PointageConfig.get().id, defaults={"staff_start_time": datetime.time(7, 30)})
    data = export(day, [
        ("1", "KIS-ENS-E01", "IN", "07:42:10"), ("2", "KIS-ENS-E01", "OUT", "12:05:00"),
        ("3", "KIS-ENS-E01", "IN", "14:58:00"), ("4", "KIS-ENS-E01", "OUT", "17:31:00"),
        ("5", "KIS-PER-P07", "IN", "06:55:00"),
        ("6", "26LT1M\nAli Diallo", "IN", "07:50:00"), ("7", "26LT1M", "IN", "12:00:00"),
        ("8", "INCONNU-99", "IN", "08:00:00"), ("9", "KIS-ENS-E01", "IN", "pas une heure"),
    ])
    summary = svc.apply_export(data)
    assert summary == {"received": 9, "applied": 7, "duplicates": 0, "unknown": 1, "errors": 1, "unknown_codes": ["INCONNU-99"]}
    t = TeacherAttendance.objects.get(teacher=ctx["teacher"], date=day)
    assert (t.entry_time, t.exit_time, t.status, t.late_minutes) == (datetime.time(7, 42, 10), datetime.time(17, 31), "LATE", 12)
    g = OtherPersonnelAttendance.objects.get(personnel=ctx["guard"], date=day)
    assert (g.entry_time, g.status) == (datetime.time(6, 55), "PRESENT")
    assert Attendance.objects.get(enrollment__student=ctx["ali"], date=day).status == "PRESENT"
    assert not Attendance.objects.filter(enrollment__student=ctx["awa"]).exists()     # pas de scan : rien d'inventé
    again = svc.apply_export(data)                                                       # relevé renvoyé : rien en double
    assert again["applied"] == 0 and again["duplicates"] == 8 and again["errors"] == 1
    assert PointageScan.objects.count() == 8                                             # l'heure illisible n'est pas gardée


def test_api_sync_requires_key(client, ctx):
    key = PointageConfig.get().api_key
    assert client.get("/api/pointage/paquet/").status_code == 403
    r = client.get(f"/api/pointage/paquet/?cle={key}")
    assert r.status_code == 200 and r.json()["format"] == svc.EXPORT_FORMAT.replace("releve", "paquet")
    body = json.dumps(export(ctx["day"], [("a1", "KIS-PER-P07", "IN", "07:00:00")]))
    assert client.post("/api/pointage/envoi/", body, content_type="application/json", HTTP_X_KIS_CLE="mauvaise").status_code == 403
    r = client.post("/api/pointage/envoi/", body, content_type="application/json", HTTP_X_KIS_CLE=key)
    assert r.status_code == 200 and r.json()["applied"] == 1 and "1 passage(s) enregistré(s)" in r.json()["message"]
    r = client.post("/api/pointage/envoi/", "{pas du json", content_type="application/json", HTTP_X_KIS_CLE=key)
    assert r.status_code == 400


def test_pointage_page_upload_and_badges(client, login, ctx):
    login(Role.ADMIN)
    page = client.get("/vie-scolaire/pointage/")
    assert page.status_code == 200 and "Télécharger le paquet de pointage" in page.content.decode()
    package = client.get("/vie-scolaire/pointage/paquet/")
    assert json.loads(package.content)["format"] == svc.PACKAGE_FORMAT
    upload = SimpleUploadedFile("pointage.json", json.dumps(export(ctx["day"], [("u1", "KIS-ENS-E01", "IN", "07:10:00")])).encode())
    r = client.post("/vie-scolaire/pointage/", {"action": "upload", "file": upload}, follow=True)
    assert "1 passage(s) enregistré(s)" in r.content.decode()
    old_key = PointageConfig.get().api_key
    client.post("/vie-scolaire/pointage/", {"action": "regen"})
    assert PointageConfig.get().api_key != old_key
    from pypdf import PdfReader
    pdf = client.get("/personnel/badges/")
    assert pdf.status_code == 200
    reader = PdfReader(BytesIO(pdf.content))
    assert "BADGE DU PERSONNEL" in reader.pages[0].extract_text() and "Keita" in reader.pages[0].extract_text()
