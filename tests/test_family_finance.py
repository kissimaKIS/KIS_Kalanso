"""V5-3 : finances regroupées par famille (3 enfants et plus, impayés par parents)."""
from decimal import Decimal

import pytest

from administration.models import Role, SchoolYear
from finance.models import FeeType, Invoice, Payment
from finance.services.grouped_payment import group_families
from pedagogie.models import Classe, EducationLevel, Enrollment, Student


@pytest.fixture
def ctx(school):
    year = SchoolYear.objects.get(school=school)
    year.validate_catalog()
    classe = Classe(school=school, school_year=year, education_level=EducationLevel.objects.get(code="LYC-10"), group="A", name="")
    classe.save()
    scol = FeeType.objects.create(name="Scolarité", category="tuition", school_year=year, amount=Decimal("90000"), is_required=True)

    def child(first, last="Diallo", **parents):
        s = Student.objects.create(first_name=first, last_name=last, **parents)
        return Enrollment.objects.create(student=s, classe=classe, school_year=year)

    a = child("Ali", father_name="Moussa Diallo", father_phone="76 41 36 30")
    b = child("Binta", father_name="M. Diallo", mother_phone="+223 76413630", mother_name="Awa Traoré")
    c = child("Cheick", father_name="m. diallo", mother_name="Awa TRAORE")   # relié à B par les noms
    d = child("Djeneba", last="Keita", father_name="Sékou Keita", father_phone="70000000")
    e = child("Fanta", last="Keita", mother_name="Fanta Ba", father_name="Sékou Keita", whatsapp_phone="70 00 00 00")
    f = child("Seul", last="Coulibaly", father_name="Adama Coulibaly")
    Payment.objects.create(invoice=Invoice.objects.get(enrollment=d, fee_type=scol), amount=Decimal("90000"))
    Payment.objects.create(invoice=Invoice.objects.get(enrollment=e, fee_type=scol), amount=Decimal("90000"))
    return dict(year=year, a=a, b=b, c=c, d=d, e=e, f=f)


def test_three_children_linked_transitively_form_one_family(ctx):
    groups = group_families(Enrollment.objects.select_related("student"))
    sizes = sorted(len(g) for g in groups)
    assert sizes == [1, 2, 3]
    big = next(g for g in groups if len(g) == 3)
    assert {e.student.first_name for e in big} == {"Ali", "Binta", "Cheick"}


def test_family_page_filters_and_totals(client, login, ctx):
    login(Role.ACCOUNTANT)
    r = client.get("/finance/familles/")
    assert r.status_code == 200
    assert [len(f["members"]) for f in r.context["families"]] == [3, 2]  # trié par reste dû
    assert r.context["families"][0]["rest"] == Decimal("270000")
    r = client.get("/finance/familles/?du=1")
    assert len(r.context["families"]) == 1
    r = client.get("/finance/familles/?tous=1")
    assert len(r.context["families"]) == 3
    r = client.get("/finance/familles/?q=76413630")
    assert len(r.context["families"]) == 1 and r.context["families"][0]["rest"] == Decimal("270000")
    r = client.get("/finance/familles/?q=fanta")
    assert len(r.context["families"]) == 1


def test_family_pdfs(client, login, ctx):
    login(Role.SECRETARY)
    r = client.get("/finance/familles/pdf/?du=1")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    r = client.get(f"/finance/famille/{ctx['a'].id}/situation/")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")


def test_teacher_has_no_access(client, login, ctx):
    login(Role.STUDIES_DIRECTOR)
    assert client.get("/finance/familles/").status_code in (302, 403)
