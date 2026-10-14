"""V5-2 : à l'inscription, encaisser plusieurs frais (inscription + 1er trimestre) sur un seul reçu."""
from decimal import Decimal

import pytest

from administration.models import Role, SchoolYear
from finance.models import FeeType, Invoice, Payment, PaymentBatch
from pedagogie.models import Classe, EducationLevel, Enrollment


@pytest.fixture
def setup(school):
    year = SchoolYear.objects.get(school=school)
    year.validate_catalog()
    classe = Classe(school=school, school_year=year, education_level=EducationLevel.objects.get(code="LYC-10"), group="A", name="")
    classe.save()
    insc = FeeType.objects.create(name="Inscription", category="registration", school_year=year, amount=Decimal("10000"), is_required=True)
    scol = FeeType.objects.create(name="Scolarité", category="tuition", school_year=year, amount=Decimal("90000"), is_required=True)
    return classe, insc, scol


def _post(classe, **extra):
    data = {"first_name": "Ali", "last_name": "Diallo", "sex": "M", "father_name": "Moussa Diallo",
            "classe": classe.id, "student_type": "regulier"}
    data.update(extra)
    return data


def test_inscription_plus_premier_trimestre_un_seul_recu(client, login, setup):
    classe, insc, scol = setup
    login(Role.ADMIN)
    response = client.post("/enrollments/new/", _post(
        classe, pay_fee=[insc.id, scol.id],
        **{f"pay_amount_{insc.id}": "10 000", f"pay_amount_{scol.id}": "30000"}))
    assert response.status_code == 302, response.content.decode()[:3000]
    batch = PaymentBatch.objects.get()
    assert response["Location"].endswith(f"?batch={batch.id}")
    assert Payment.objects.filter(batch=batch).count() == 2
    assert batch.total == Decimal("40000")
    enrollment = Enrollment.objects.get()
    assert Invoice.objects.get(enrollment=enrollment, fee_type=scol).reste == Decimal("60000")


def test_frais_non_coche_ignore_et_sans_paiement_pas_de_recu(client, login, setup):
    classe, insc, scol = setup
    login(Role.ADMIN)
    response = client.post("/enrollments/new/", _post(classe, **{f"pay_amount_{scol.id}": "30000"}))
    assert response.status_code == 302
    assert not PaymentBatch.objects.exists() and not Payment.objects.exists()


def test_depassement_annule_toute_l_inscription(client, login, setup):
    classe, insc, scol = setup
    login(Role.ADMIN)
    response = client.post("/enrollments/new/", _post(
        classe, pay_fee=[insc.id, scol.id],
        **{f"pay_amount_{insc.id}": "10000", f"pay_amount_{scol.id}": "999999"}))
    assert response.status_code == 200
    assert not Enrollment.objects.exists() and not Payment.objects.exists()
    assert "[" not in response.context["form"].non_field_errors()[0]
