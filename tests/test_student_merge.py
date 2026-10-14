"""Doublons d'élèves (07/10) : repérage et fusion de fiches créées par un import incomplet."""
import datetime
from decimal import Decimal

import pytest

from administration.models import CorrectionLog, Role, SchoolYear
from administration.services.student_matching import find_duplicates
from finance.models import FeeType, Invoice, Payment
from pedagogie.models import Classe, EducationLevel, Enrollment, Student
from vie_scolaire.models import Attendance


@pytest.fixture
def ctx(school):
    year = SchoolYear.objects.get(school=school)
    year.validate_catalog()
    lvl = EducationLevel.objects.get(code="LYC-10")
    a = Classe(school=school, school_year=year, education_level=lvl, group="A", name=""); a.save()
    b = Classe(school=school, school_year=year, education_level=lvl, group="B", name=""); b.save()
    insc = FeeType.objects.create(name="Inscription", category="registration", school_year=year, amount=Decimal("10000"), is_required=True)
    # Premier import (fichier incomplet) puis second import (complété) : deux fiches.
    old = Student.objects.create(first_name="Moussa Makan", last_name="DEMBELE", father_phone="73167778")
    new = Student.objects.create(first_name="Moussa Makan", last_name="Dembélé", father_phone="73 16 77 78",
                                 matricule="48", date_of_birth=datetime.date(2017, 3, 29))
    e_old = Enrollment.objects.create(student=old, classe=a, school_year=year)
    e_new = Enrollment.objects.create(student=new, classe=a, school_year=year)
    alim = Student.objects.create(first_name="Alimamy Kounta", last_name="TRAORE", matricule="49", father_phone="73242967")
    alma = Student.objects.create(first_name="Almamy Kounta", last_name="TRAORE", father_phone="73242967")
    # Vrais homonymes : rien en commun.
    Student.objects.create(first_name="Fatoumata", last_name="TRAORE", father_phone="70000001", date_of_birth=datetime.date(2015, 1, 1))
    Student.objects.create(first_name="Fatoumata", last_name="TRAORE", father_phone="70000002", date_of_birth=datetime.date(2016, 5, 5))
    return dict(year=year, a=a, b=b, insc=insc, old=old, new=new, e_old=e_old, e_new=e_new, alim=alim, alma=alma)


def test_duplicates_found_but_real_homonyms_left_alone(ctx):
    pairs = {frozenset((p["keep"].pk, p["drop"].pk)): p for p in find_duplicates()}
    moussa = pairs[frozenset((ctx["old"].pk, ctx["new"].pk))]
    assert moussa["keep"] == ctx["new"]                      # la fiche la plus complète est proposée
    assert "même téléphone de parent" in moussa["reasons"]
    assert frozenset((ctx["alim"].pk, ctx["alma"].pk)) in pairs  # Alimamy / Almamy
    fatous = [p for p in pairs.values() if p["keep"].first_name == "Fatoumata"]
    assert not fatous                                        # dates de naissance différentes


def test_merge_same_class_same_year_keeps_money_and_history(client, login, ctx):
    old_inv = Invoice.objects.get(enrollment=ctx["e_old"], fee_type=ctx["insc"])
    Payment.objects.create(invoice=old_inv, amount=Decimal("6000"))
    Attendance.objects.create(enrollment=ctx["e_old"], date=ctx["year"].start_date, status="ABSENT")
    login(Role.DIRECTOR)
    url = f"/corrections/fusion/{ctx['new'].pk}/{ctx['old'].pk}/"
    page = client.get(url).content.decode()
    assert "réunies" in page
    r = client.post(url, {"reason": "doublon import"})
    assert r.status_code == 302, r.context.get("error")
    assert not Student.objects.filter(pk=ctx["old"].pk).exists()
    keep = Student.objects.get(pk=ctx["new"].pk)
    assert keep.enrollments.count() == 1
    inv = Invoice.objects.get(enrollment__student=keep, fee_type=ctx["insc"])
    assert inv.paid_amount == Decimal("6000") and inv.payments.count() == 1
    assert Attendance.objects.get().enrollment.student == keep
    assert CorrectionLog.objects.get().action == CorrectionLog.Action.STUDENT_MERGE


def test_merge_fills_empty_fields_and_never_overwrites(ctx):
    from administration.services.student_merge import merge_students
    ctx["alma"].mother_name = "Awa Diarra"; ctx["alma"].matricule = None; ctx["alma"].save()
    merge_students(ctx["alim"], ctx["alma"], "doublon")
    keep = Student.objects.get(pk=ctx["alim"].pk)
    assert keep.first_name == "Alimamy Kounta" and keep.matricule == "49" and keep.mother_name == "Awa Diarra"


def test_merge_moves_matricule_when_keep_has_none(ctx):
    from administration.services.student_merge import merge_students
    merge_students(ctx["old"], ctx["new"], "doublon")
    keep = Student.objects.get(pk=ctx["old"].pk)
    assert keep.matricule == "48" and keep.date_of_birth == datetime.date(2017, 3, 29)


def test_merge_refused_when_two_different_classes_same_year(client, login, ctx):
    ctx["e_old"].classe = ctx["b"]; ctx["e_old"].save()
    login(Role.ADMIN)
    r = client.post(f"/corrections/fusion/{ctx['new'].pk}/{ctx['old'].pk}/", {"reason": "doublon"})
    assert r.status_code == 200 and "deux classes différentes" in r.content.decode()
    assert Student.objects.filter(pk=ctx["old"].pk).exists()


def test_pages_and_permissions(client, login, ctx):
    login(Role.ADMIN)
    page = client.get("/corrections/doublons/").content.decode()
    assert "Moussa Makan" in page and "Examiner et fusionner" in page
    assert "Almamy" in client.get(f"/corrections/fusion/{ctx['alim'].pk}/").content.decode()
    assert "Fusionner avec une autre fiche" in client.get(f"/students/{ctx['new'].pk}/").content.decode()
    client.logout()
    login(Role.SECRETARY, username="sec")
    assert client.get("/corrections/doublons/").status_code in (302, 403)
