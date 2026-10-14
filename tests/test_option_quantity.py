"""V5-8 : une seule option « Uniforme » avec quantité et prix unitaire variables."""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from administration.models import Role, SchoolYear
from finance.models import FeeType, Invoice, Payment, StudentOption
from finance.services.options import add_option, update_option
from pedagogie.models import Classe, EducationLevel, Enrollment


@pytest.fixture
def ctx(school):
    year = SchoolYear.objects.get(school=school)
    year.validate_catalog()
    classe = Classe(school=school, school_year=year, education_level=EducationLevel.objects.get(code="LYC-10"), group="A", name="")
    classe.save()
    uniforme = FeeType.objects.create(name="Uniforme", category="optional", school_year=year, amount=Decimal("7500"), allows_quantity=True)
    cantine = FeeType.objects.create(name="Cantine", category="optional", school_year=year, amount=Decimal("15000"))
    return dict(year=year, classe=classe, uniforme=uniforme, cantine=cantine)


def test_enrollment_with_three_uniforms_at_custom_price(client, login, ctx):
    login(Role.ADMIN)
    u, c = ctx["uniforme"], ctx["cantine"]
    r = client.post("/enrollments/new/", {
        "first_name": "Ali", "last_name": "Diallo", "sex": "M", "classe": ctx["classe"].id, "student_type": "regulier",
        "optional_fees": [u.id, c.id], f"option_qty_{u.id}": "3", f"option_price_{u.id}": "8 000",
        f"option_qty_{c.id}": "5",  # ignoré : la cantine n'est pas une option à quantité
    })
    assert r.status_code == 302, r.content.decode()[:2000]
    e = Enrollment.objects.get()
    opt = StudentOption.objects.get(enrollment=e, fee_type=u)
    assert (opt.quantity, opt.unit_price) == (3, Decimal("8000"))
    inv = Invoice.objects.get(enrollment=e, fee_type=u)
    assert inv.total_amount == Decimal("24000") and inv.label == "Uniforme (3 × 8 000)"
    assert Invoice.objects.get(enrollment=e, fee_type=c).total_amount == Decimal("15000")
    assert Invoice.objects.get(enrollment=e, fee_type=c).label == "Cantine"


def test_default_price_and_invalid_quantity(client, login, ctx):
    login(Role.ADMIN)
    u = ctx["uniforme"]
    base = {"first_name": "Ali", "last_name": "Diallo", "sex": "M", "classe": ctx["classe"].id, "student_type": "regulier", "optional_fees": [u.id]}
    r = client.post("/enrollments/new/", {**base, f"option_qty_{u.id}": "0"})
    assert r.status_code == 200 and not Enrollment.objects.exists()
    r = client.post("/enrollments/new/", {**base, f"option_qty_{u.id}": "2", f"option_price_{u.id}": ""})
    assert r.status_code == 302
    assert Invoice.objects.get(fee_type=u).total_amount == Decimal("15000")


def test_update_quantity_later_and_never_below_paid(ctx):
    e = Enrollment.objects.create(student_id=_student().id, classe=ctx["classe"], school_year=ctx["year"])
    opt = add_option(e, ctx["uniforme"], 2, Decimal("7500"))
    inv = Invoice.objects.get(enrollment=e, fee_type=ctx["uniforme"])
    Payment.objects.create(invoice=inv, amount=Decimal("15000"))
    update_option(opt, 3, Decimal("7500"))
    inv.refresh_from_db()
    assert inv.total_amount == Decimal("22500") and inv.reste == Decimal("7500")
    with pytest.raises(ValidationError):
        update_option(opt, 1, Decimal("7500"))


def test_financial_adjustment_adds_and_updates_quantity_options(client, login, ctx):
    login(Role.ADMIN)
    e = Enrollment.objects.create(student_id=_student().id, classe=ctx["classe"], school_year=ctx["year"])
    u = ctx["uniforme"]
    from django.urls import reverse
    url = reverse("financial_adjustment", args=[e.id])
    assert f"option_qty_{u.id}" in client.get(url).content.decode()
    r = client.post(url, {"optional_fees": [u.id], f"option_qty_{u.id}": "2", f"option_price_{u.id}": "9000"})
    assert r.status_code == 302
    assert Invoice.objects.get(enrollment=e, fee_type=u).total_amount == Decimal("18000")
    r = client.post(url, {f"current_qty_{u.id}": "4", f"current_price_{u.id}": "9000"})
    assert r.status_code == 302
    assert Invoice.objects.get(enrollment=e, fee_type=u).total_amount == Decimal("36000")


def test_fee_form_quantity_reserved_to_options(ctx):
    from finance.forms import FeeTypeForm
    base = {"name": "Tenue", "amount": "5000", "registration_scope": "annual"}
    assert FeeTypeForm({**base, "category": "optional", "allows_quantity": "on"}).is_valid()
    form = FeeTypeForm({**base, "category": "tuition", "allows_quantity": "on"})
    assert not form.is_valid() and "allows_quantity" in form.errors


def _student():
    from pedagogie.models import Student
    return Student.objects.create(first_name="Binta", last_name="Keita")
