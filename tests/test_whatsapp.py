"""Envoi assisté par WhatsApp (V8-6) : liens wa.me avec message prérempli."""
from decimal import Decimal
from urllib.parse import unquote

import pytest

from administration.models import Role, SchoolYear
from common import whatsapp
from communication.models import Announcement
from finance.models import FeeType, Invoice
from finance.services.grouped_payment import record_grouped_payment
from pedagogie.models import Classe, EducationLevel, Enrollment, Student, Term
from vie_scolaire.models import DisciplineIncident


def test_phone_normalisation():
    assert whatsapp.normalize_phone("76 41 36 30") == "22376413630"
    assert whatsapp.normalize_phone("+223 76-41-36-30") == "22376413630"
    assert whatsapp.normalize_phone("0022376413630") == "22376413630"
    assert whatsapp.normalize_phone("+33 6 12 34 56 78") == "33612345678"
    assert whatsapp.normalize_phone("1234") == "" and whatsapp.wa_url("", "x") == ""
    assert whatsapp.wa_url("76413630", "Bonjour à tous").startswith("https://wa.me/22376413630?text=Bonjour%20%C3%A0")


@pytest.fixture
def ctx(school):
    year = SchoolYear.objects.get(school=school)
    year.validate_catalog()
    lvl = EducationLevel.objects.get(code="LYC-10")
    a = Classe(school=school, school_year=year, education_level=lvl, group="A", name=""); a.save()
    fee = FeeType.objects.create(name="Scolarité", category="tuition", school_year=year, amount=Decimal("90000"), is_required=True)
    ali = Student.objects.create(first_name="Ali", last_name="Diallo", father_name="Moussa Diallo", father_phone="76413630")
    awa = Student.objects.create(first_name="Awa", last_name="Diallo", father_name="Moussa Diallo", father_phone="76 41 36 30",
                                 whatsapp_phone="66000000")
    sans = Student.objects.create(first_name="Sidi", last_name="Ba")
    es = [Enrollment.objects.create(student=s, classe=a, school_year=year) for s in (ali, awa, sans)]
    return dict(year=year, classe=a, fee=fee, ali=ali, awa=awa, es=es, school=school)


def test_announcement_one_line_per_family(client, login, ctx):
    a = Announcement.objects.create(title="Réunion des parents", message="Samedi à 9 h", audience="PARENTS")
    login(Role.ADMIN)
    assert f"/communication/{a.id}/whatsapp/" in client.get("/communication/").content.decode()
    r = client.get(f"/communication/{a.id}/whatsapp/")
    rows = r.context["rows"]
    assert len(rows) == 2 and r.context["without_phone"] == 1                 # Ali + Awa = une famille ; Sidi sans numéro
    family = next(row for row in rows if row["url"])
    assert "Ali" in family["detail"] and "Awa" in family["detail"]
    assert "Réunion des parents" in unquote(family["url"]) and "Samedi à 9 h" in unquote(family["url"])


def test_receipt_balance_discipline_and_bulletin_links(client, login, ctx):
    login(Role.ADMIN)
    inv = Invoice.objects.get(enrollment=ctx["es"][0], fee_type=ctx["fee"])
    batch = record_grouped_payment([(inv, Decimal("30000"))])
    page = client.get(f"/finance/encaissement/termine/?batch={batch.id}")
    url = unquote(page.context["whatsapp_url"])
    assert url.startswith("https://wa.me/22376413630") and batch.receipt_number in url and "30 000" in url and "reste 60 000" in url
    assert "data-wa-pdf" in page.content.decode()
    page = client.get(f"/students/{ctx['awa'].id}/")
    assert unquote(page.context["whatsapp_balance_url"]).startswith("https://wa.me/22366000000")   # numéro WhatsApp prioritaire
    DisciplineIncident.objects.create(enrollment=ctx["es"][0], description="Retard répété", action="Avertissement")
    page = client.get("/vie-scolaire/discipline/")
    assert "Retard répété" in unquote(page.content.decode()) and "kis-btn-whatsapp" in page.content.decode()
    term = Term.objects.filter(school_year=ctx["year"]).first() or Term.objects.create(school_year=ctx["year"], name="1er trimestre", order=1)
    page = client.get(f"/pedagogie/classes/{ctx['classe'].id}/terms/{term.id}/bulletins/")
    html = page.content.decode()
    assert "kis-btn-whatsapp" in html and f"/bulletin" in html and "data-wa-pdf" in html
