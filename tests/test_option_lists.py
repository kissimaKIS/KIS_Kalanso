"""V5-7 : listes d'élèves par option (cantine, transport, uniforme) et impression."""
from decimal import Decimal

import pytest

from administration.models import Role, SchoolYear
from finance.models import FeeType, Invoice, Payment
from finance.services.options import add_option
from pedagogie.models import Classe, EducationLevel, Enrollment, Student


@pytest.fixture
def ctx(school):
    year = SchoolYear.objects.get(school=school)
    year.validate_catalog()
    lvl = EducationLevel.objects.get(code="LYC-10")
    a = Classe(school=school, school_year=year, education_level=lvl, group="A", name=""); a.save()
    b = Classe(school=school, school_year=year, education_level=lvl, group="B", name=""); b.save()
    cantine = FeeType.objects.create(name="Cantine", category="optional", school_year=year, amount=Decimal("15000"))
    uniforme = FeeType.objects.create(name="Uniforme", category="optional", school_year=year, amount=Decimal("7500"), allows_quantity=True)
    enrollments = []
    for name, classe in (("Ali", a), ("Binta", a), ("Cheick", b)):
        e = Enrollment.objects.create(student=Student.objects.create(first_name=name, last_name="Diallo"), classe=classe, school_year=year)
        enrollments.append(e)
    add_option(enrollments[0], cantine); add_option(enrollments[2], cantine)
    add_option(enrollments[0], uniforme, 2, Decimal("8000")); add_option(enrollments[1], uniforme, 3, Decimal("7500"))
    Payment.objects.create(invoice=Invoice.objects.get(enrollment=enrollments[0], fee_type=cantine), amount=Decimal("15000"))
    return dict(year=year, a=a, b=b, cantine=cantine, uniforme=uniforme)


def test_list_by_option_with_class_and_status_filters(client, login, ctx):
    login(Role.ADMIN)
    page = client.get(f"/finance/options/?option={ctx['cantine'].id}").content.decode()
    assert "Ali" in page and "Cheick" in page and "Binta" not in page
    page = client.get(f"/finance/options/?option={ctx['cantine'].id}&classe={ctx['b'].id}").content.decode()
    assert "Cheick" in page and "Ali" not in page
    page = client.get(f"/finance/options/?option={ctx['cantine'].id}&statut=du").content.decode()
    assert "Cheick" in page and ">Diallo Ali<" not in page


def test_uniform_list_shows_quantities_and_total(client, login, ctx):
    login(Role.ADMIN)
    r = client.get(f"/finance/options/?option={ctx['uniforme'].id}")
    assert r.context["totals"]["quantity"] == 5
    assert r.context["totals"]["total"] == Decimal("38500")


def test_pdf_with_and_without_amounts(client, login, ctx):
    login(Role.SECRETARY)
    for extra in ("", "&montants=0"):
        r = client.get(f"/finance/options/pdf/?option={ctx['uniforme'].id}{extra}")
        assert r.status_code == 200 and r.content.startswith(b"%PDF")


def test_studies_director_sees_list_without_amounts(client, login, ctx):
    login(Role.STUDIES_DIRECTOR)
    r = client.get(f"/finance/options/?option={ctx['cantine'].id}")
    assert r.status_code == 200 and not r.context["show_money"]
    client.logout()
    login(Role.TEACHER, username="prof")
    assert client.get("/finance/options/").status_code in (302, 403)
