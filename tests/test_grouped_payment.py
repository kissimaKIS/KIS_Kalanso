"""Encaissement groupé : plusieurs factures, plusieurs enfants d'une famille, un seul reçu."""
from decimal import Decimal

import pytest

from administration.models import Role, SchoolYear
from finance.models import FeeType, Invoice, Payment, PaymentBatch
from finance.services.grouped_payment import family_enrollments, record_grouped_payment
from pedagogie.models import Classe, EducationLevel, Enrollment, Student


@pytest.fixture
def famille(school):
    year = SchoolYear.objects.get(school=school)
    year.validate_catalog()
    classe = Classe(school=school, school_year=year, education_level=EducationLevel.objects.get(code="LYC-10"), group="A", name="")
    classe.save()
    inscription = FeeType.objects.create(name="Inscription", category="registration", school_year=year, amount=Decimal("10000"))
    scolarite = FeeType.objects.create(name="Scolarité", category="tuition", school_year=year, amount=Decimal("90000"))
    option = FeeType.objects.create(name="Cantine", category="other", school_year=year, amount=Decimal("15000"))

    def child(first, phone="", father="Moussa Diallo", mother="Awa Traoré"):
        s = Student.objects.create(first_name=first, last_name="Diallo", father_name=father, mother_name=mother, father_phone=phone)
        e = Enrollment.objects.create(student=s, classe=classe, school_year=year)
        for fee in (inscription, scolarite, option):
            Invoice.objects.get_or_create(enrollment=e, fee_type=fee, defaults={"total_amount": fee.amount})
        return e

    a = child("Ali", phone="+223 76 41 36 30")
    b = child("Binta", phone="76413630", father="M. Diallo", mother="")     # même téléphone
    c = child("Cheick", father="Moussa  DIALLO", mother="awa traore")       # mêmes noms (casse/accents)
    other = child("Djeneba", phone="70000000", father="Sékou Keita", mother="Fanta Ba")
    return {"a": a, "b": b, "c": c, "other": other}


def test_siblings_are_detected_by_phone_or_both_parent_names(famille):
    found = {e.student.first_name for e in family_enrollments(famille["a"])}
    assert found == {"Ali", "Binta", "Cheick"}
    assert {e.student.first_name for e in family_enrollments(famille["other"])} == {"Djeneba"}


def test_one_receipt_for_several_fees_and_children(famille):
    a, b = famille["a"], famille["b"]
    ins_a = a.invoices.get(fee_type__name="Inscription")
    sco_a = a.invoices.get(fee_type__name="Scolarité")
    ins_b = b.invoices.get(fee_type__name="Inscription")
    batch = record_grouped_payment([(ins_a, Decimal("10000")), (sco_a, Decimal("30000")), (ins_b, Decimal("10000"))], "Moussa Diallo")
    assert batch.payments.count() == 3 and batch.total == Decimal("50000")
    sco_a.refresh_from_db()
    assert sco_a.paid_amount == Decimal("30000") and sco_a.reste == Decimal("60000")  # tranche
    numbers = list(batch.payments.values_list("receipt_number", flat=True))
    assert all(n.startswith(batch.receipt_number + "/") for n in numbers)


def test_numbering_is_not_disturbed_by_grouped_lines(famille):
    a = famille["a"]
    batch = record_grouped_payment([(a.invoices.get(fee_type__name="Inscription"), Decimal("10000")),
                                    (a.invoices.get(fee_type__name="Cantine"), Decimal("15000"))])
    single = Payment(invoice=a.invoices.get(fee_type__name="Scolarité"), amount=Decimal("1000"))
    single.save()
    first = int(batch.receipt_number.rsplit("-", 1)[1])
    assert single.receipt_number.endswith(f"{first + 1:05d}")


def test_all_or_nothing_when_one_line_exceeds_the_balance(famille):
    a = famille["a"]
    with pytest.raises(Exception):
        record_grouped_payment([(a.invoices.get(fee_type__name="Inscription"), Decimal("10000")),
                                (a.invoices.get(fee_type__name="Cantine"), Decimal("99999"))])
    assert not Payment.objects.exists() and not PaymentBatch.objects.exists()


def test_pages_grouped_payment_done_and_pdfs(client, login, famille):
    login(Role.ACCOUNTANT)
    a = famille["a"]
    assert "Diallo" in client.get("/finance/payments/new/?q=76413630").content.decode()
    html = client.get(f"/finance/encaissement/{a.id}/").content.decode()
    assert "Régler aussi les frères et sœurs" in html
    html = client.get(f"/finance/encaissement/{a.id}/?famille=1").content.decode()
    assert "Binta" in html and "Cheick" in html
    ins_c = famille["c"].invoices.get(fee_type__name="Inscription")
    sco_a = a.invoices.get(fee_type__name="Scolarité")
    response = client.post(f"/finance/encaissement/{a.id}/", {
        "famille": "1", "invoice": [ins_c.id, sco_a.id],
        f"amount_{ins_c.id}": "10 000", f"amount_{sco_a.id}": "45000", "payer_name": "Awa Traoré",
    })
    batch = PaymentBatch.objects.get()
    assert response.status_code == 302 and response.url.endswith(f"?batch={batch.id}")
    done = client.get(response.url).content.decode()
    assert batch.receipt_number in done and 'target="_blank"' in done and "55" in done
    for url in (f"/finance/recus/{batch.id}/", f"/finance/payments/{batch.payments.first().id}/receipt/",
                f"/finance/famille/{a.id}/situation/"):
        r = client.get(url)
        assert r["Content-Type"] == "application/pdf" and r.content.startswith(b"%PDF")


def test_errors_are_shown_and_nothing_saved(client, login, famille):
    login(Role.ACCOUNTANT)
    a = famille["a"]
    inv = a.invoices.get(fee_type__name="Cantine")
    html = client.post(f"/finance/encaissement/{a.id}/", {"invoice": [inv.id], f"amount_{inv.id}": "20000"}).content.decode()
    assert "dépasse le reste" in html and not Payment.objects.exists()
    html = client.post(f"/finance/encaissement/{a.id}/", {}).content.decode()
    assert "Cochez au moins une facture" in html


def test_single_payment_goes_to_confirmation_page(client, login, famille):
    login(Role.ACCOUNTANT)
    inv = famille["a"].invoices.get(fee_type__name="Inscription")
    response = client.post(f"/finance/invoices/{inv.id}/payment/", {"amount": "5000"})
    assert "/finance/encaissement/termine/?payment=" in response.url


def test_enrollment_forms_blank_and_per_student(client, login, famille):
    login(Role.SECRETARY)
    for url in ("/enrollments/fiche-inscription/vierge/", f"/enrollments/{famille['a'].id}/fiche-inscription/"):
        r = client.get(url)
        assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert "fiche-inscription/vierge" in client.get("/enrollments/new/").content.decode()
    assert f"/enrollments/{famille['a'].id}/fiche-inscription/" in client.get(f"/students/{famille['a'].student_id}/").content.decode()
