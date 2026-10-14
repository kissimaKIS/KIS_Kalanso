"""V5-10 : corrections réservées à la direction (annulation, suppression, changement de classe)."""
from decimal import Decimal

import pytest

from administration.models import CorrectionLog, Role, SchoolYear
from finance.models import FeeType, Invoice, Payment, PaymentBatch, StudentOption
from finance.services.grouped_payment import record_grouped_payment
from pedagogie.models import Classe, EducationLevel, Enrollment, Student


@pytest.fixture
def ctx(school):
    year = SchoolYear.objects.get(school=school)
    year.validate_catalog()
    lvl10 = EducationLevel.objects.get(code="LYC-10")
    c10a = Classe(school=school, school_year=year, education_level=lvl10, group="A", name=""); c10a.save()
    c10b = Classe(school=school, school_year=year, education_level=lvl10, group="B", name=""); c10b.save()
    other_level = EducationLevel.objects.filter(school_type=lvl10.school_type).exclude(pk=lvl10.pk).first()
    c11 = Classe(school=school, school_year=year, education_level=other_level, group="A", name=""); c11.save()
    insc = FeeType.objects.create(name="Inscription", category="registration", school_year=year, amount=Decimal("10000"), is_required=True)
    scol10 = FeeType.objects.create(name="Scolarité 10e", category="tuition", school_year=year, amount=Decimal("90000"), is_required=True, education_level=lvl10)
    scol11 = FeeType.objects.create(name="Scolarité 11e", category="tuition", school_year=year, amount=Decimal("95000"), is_required=True, education_level=other_level)
    cantine = FeeType.objects.create(name="Cantine", category="optional", school_year=year, amount=Decimal("15000"))
    student = Student.objects.create(first_name="Ali", last_name="Diallo")
    e = Enrollment.objects.create(student=student, classe=c10a, school_year=year)
    StudentOption.objects.create(enrollment=e, fee_type=cantine)
    return dict(year=year, c10a=c10a, c10b=c10b, c11=c11, e=e, student=student,
                insc=insc, scol10=scol10, scol11=scol11, cantine=cantine)


def inv(e, fee):
    return Invoice.objects.get(enrollment=e, fee_type=fee)


def test_only_direction_has_the_permission(client, login, ctx):
    login(Role.SECRETARY)
    assert client.get(f"/corrections/supprimer-eleve/{ctx['student'].id}/").status_code in (302, 403)
    assert client.get("/corrections/journal/").status_code in (302, 403)
    client.logout()
    login(Role.ACCOUNTANT, username="compta")
    assert client.get(f"/corrections/supprimer-facture/{inv(ctx['e'], ctx['insc']).id}/").status_code in (302, 403)
    client.logout()
    login(Role.DIRECTOR, username="dir")
    assert client.get(f"/corrections/supprimer-facture/{inv(ctx['e'], ctx['insc']).id}/").status_code == 200


def test_cancel_payment_restores_balance_and_number_is_never_reused(client, login, ctx):
    login(Role.ADMIN)
    i = inv(ctx["e"], ctx["insc"])
    p = Payment.objects.create(invoice=i, amount=Decimal("10000"))
    number = p.receipt_number
    r = client.post(f"/corrections/annuler-paiement/{p.id}/", {"reason": "erreur de saisie"})
    assert r.status_code == 302
    i.refresh_from_db()
    assert i.paid_amount == 0 and not Payment.objects.exists()
    log = CorrectionLog.objects.get()
    assert log.receipt_number == number and log.amount == Decimal("10000") and log.reason == "erreur de saisie"
    p2 = Payment.objects.create(invoice=i, amount=Decimal("5000"))
    assert p2.receipt_number != number


def test_cancel_last_line_of_batch_removes_the_batch(ctx):
    e = ctx["e"]
    batch = record_grouped_payment([(inv(e, ctx["insc"]), Decimal("10000")), (inv(e, ctx["scol10"]), Decimal("30000"))])
    from administration.services.corrections import cancel_payment
    first, second = batch.payments.order_by("id")
    cancel_payment(first, "doublon")
    assert PaymentBatch.objects.filter(pk=batch.pk).exists()
    cancel_payment(second, "doublon")
    assert not PaymentBatch.objects.exists()


def test_reason_is_mandatory(client, login, ctx):
    login(Role.ADMIN)
    i = inv(ctx["e"], ctx["cantine"])
    r = client.post(f"/corrections/supprimer-facture/{i.id}/", {"reason": ""})
    assert r.status_code == 200 and "motif" in r.content.decode()
    assert Invoice.objects.filter(pk=i.pk).exists()


def test_delete_invoice_refused_with_payments_and_removes_option(client, login, ctx):
    login(Role.ADMIN)
    e = ctx["e"]
    paid = inv(e, ctx["insc"])
    Payment.objects.create(invoice=paid, amount=Decimal("1000"))
    r = client.post(f"/corrections/supprimer-facture/{paid.id}/", {"reason": "créée par erreur"})
    assert r.status_code == 200 and Invoice.objects.filter(pk=paid.pk).exists()
    assert "annulez" in r.content.decode().lower()
    option = inv(e, ctx["cantine"])
    r = client.post(f"/corrections/supprimer-facture/{option.id}/", {"reason": "créée par erreur"})
    assert r.status_code == 302
    assert not Invoice.objects.filter(pk=option.pk).exists()
    assert not StudentOption.objects.filter(enrollment=e).exists()


def test_change_class_same_level_keeps_invoices(client, login, ctx):
    login(Role.ADMIN)
    e = ctx["e"]
    Payment.objects.create(invoice=inv(e, ctx["scol10"]), amount=Decimal("30000"))
    r = client.post(f"/corrections/changer-classe/{e.id}/", {"classe": ctx["c10b"].id, "reason": "mauvais groupe"})
    assert r.status_code == 302
    e.refresh_from_db()
    assert e.classe == ctx["c10b"]
    assert inv(e, ctx["scol10"]).paid_amount == Decimal("30000")
    assert CorrectionLog.objects.get().action == CorrectionLog.Action.CLASS_CHANGE


def test_change_level_replaces_unpaid_tuition_and_refuses_paid_one(client, login, ctx):
    login(Role.ADMIN)
    e = ctx["e"]
    page = client.get(f"/corrections/changer-classe/{e.id}/?classe={ctx['c11'].id}").content.decode()
    assert "Scolarité 10e" in page and "Scolarité 11e" in page
    r = client.post(f"/corrections/changer-classe/{e.id}/", {"classe": ctx["c11"].id, "reason": "mauvaise classe"})
    assert r.status_code == 302
    assert set(e.invoices.values_list("fee_type__name", flat=True)) == {"Inscription", "Scolarité 11e", "Cantine"}
    # Retour en 10e alors que la scolarité 11e est déjà payée : refusé.
    Payment.objects.create(invoice=inv(e, ctx["scol11"]), amount=Decimal("5000"))
    r = client.post(f"/corrections/changer-classe/{e.id}/", {"classe": ctx["c10a"].id, "reason": "retour"})
    assert r.status_code == 200
    e.refresh_from_db()
    assert e.classe == ctx["c11"]


def test_delete_enrollment_and_student(client, login, ctx):
    login(Role.ADMIN)
    e, student = ctx["e"], ctx["student"]
    p = Payment.objects.create(invoice=inv(e, ctx["insc"]), amount=Decimal("10000"))
    r = client.post(f"/corrections/supprimer-eleve/{student.id}/", {"reason": "doublon"})
    assert r.status_code == 200 and Student.objects.filter(pk=student.pk).exists()
    client.post(f"/corrections/annuler-paiement/{p.id}/", {"reason": "doublon"})
    r = client.post(f"/corrections/supprimer-inscription/{e.id}/", {"reason": "inscrit par erreur"})
    assert r.status_code == 302 and not Enrollment.objects.exists() and not Invoice.objects.exists()
    assert Student.objects.filter(pk=student.pk).exists()
    r = client.post(f"/corrections/supprimer-eleve/{student.id}/", {"reason": "doublon"})
    assert r.status_code == 302 and not Student.objects.exists()
    assert CorrectionLog.objects.count() == 3
    assert "doublon" in client.get("/corrections/journal/").content.decode()


def test_closed_year_cannot_be_corrected(client, login, ctx):
    login(Role.ADMIN)
    SchoolYear.objects.filter(pk=ctx["year"].pk).update(is_closed=True)
    i = inv(ctx["e"], ctx["cantine"])
    r = client.post(f"/corrections/supprimer-facture/{i.id}/", {"reason": "erreur"})
    assert r.status_code == 200 and Invoice.objects.filter(pk=i.pk).exists()


def test_student_detail_shows_correction_buttons_only_to_direction(client, login, ctx):
    login(Role.ADMIN)
    Payment.objects.create(invoice=inv(ctx["e"], ctx["insc"]), amount=Decimal("1000"))
    page = client.get(f"/students/{ctx['student'].id}/").content.decode()
    assert "Changer de classe" in page and ("Supprimer l&#x27;élève" in page or "Supprimer l'élève" in page)
    assert "Paiements enregistrés" in page and "annuler-paiement" in page
    client.logout()
    login(Role.SECRETARY, username="sec")
    page = client.get(f"/students/{ctx['student'].id}/").content.decode()
    assert "Changer de classe" not in page and "annuler-paiement" not in page
