"""Retours du 09/10 : frais global détaillé en postes (inscription + manuel + uniformes),
ventilation des versements, application aux inscriptions existantes ; documents par
classe ; annonces modifiables."""
from decimal import Decimal

import pytest

from administration.models import Role, SchoolYear
from finance.models import FeeType, Invoice, InvoiceLine, Payment, PaymentBatch
from finance.services import components as svc
from finance.services.grouped_payment import record_grouped_payment
from pedagogie.models import Classe, EducationLevel, Enrollment, Student

D = Decimal


@pytest.fixture
def ctx(school):
    year = SchoolYear.objects.get(school=school)
    year.validate_catalog()
    classe = Classe(school=school, school_year=year, education_level=EducationLevel.objects.get(code="LYC-10"), group="A", name="")
    classe.save()
    fee = FeeType.objects.create(name="Inscription", category="registration", school_year=year, amount=D("20000"), is_required=True)
    scol = FeeType.objects.create(name="Scolarité", category="tuition", school_year=year, amount=D("90000"), is_required=True)
    return dict(year=year, classe=classe, fee=fee, scol=scol)


def detail(fee):
    svc.save_components(fee, [(None, "Frais d'inscription", D("8000")), (None, "Manuel", D("5000")),
                              (None, "2 uniformes", D("7000"))])


def enroll(ctx, first="Awa"):
    s = Student.objects.create(first_name=first, last_name="Diarra", sex="F")
    return Enrollment.objects.create(student=s, classe=ctx["classe"], school_year=ctx["year"])


def lines_of(invoice):
    return [(l.name, l.amount, l.paid_amount) for l in InvoiceLine.objects.filter(invoice=invoice).order_by("order")]


# ---------------------------------------------------------------- postes et paiement
def test_new_enrollment_gets_the_lines_and_payment_chooses_them(ctx):
    detail(ctx["fee"])
    ctx["fee"].refresh_from_db()
    assert ctx["fee"].amount == D("20000")
    e = enroll(ctx)
    inv = e.invoices.get(fee_type=ctx["fee"])
    assert inv.total_amount == D("20000")
    assert lines_of(inv) == [("Frais d'inscription", D("8000"), 0), ("Manuel", D("5000"), 0), ("2 uniformes", D("7000"), 0)]
    l1, l2, l3 = inv.lines.order_by("order")
    sco = e.invoices.get(fee_type=ctx["scol"])
    batch = record_grouped_payment([(inv, D("15000"), [(l1, D("8000")), (l3, D("7000"))]), (sco, D("30000"))])
    assert batch.payments.count() == 2                          # un seul reçu global
    inv.refresh_from_db()
    assert inv.paid_amount == D("15000") and inv.reste == D("5000")
    assert lines_of(inv) == [("Frais d'inscription", D("8000"), D("8000")), ("Manuel", D("5000"), 0), ("2 uniformes", D("7000"), D("7000"))]
    # Sans choix : réparti dans l'ordre des postes.
    Payment.objects.create(invoice=inv, amount=D("3000"))
    assert InvoiceLine.objects.get(pk=l2.pk).paid_amount == D("3000")


def test_lines_must_match_amount_and_not_exceed_rest(ctx):
    from django.core.exceptions import ValidationError
    detail(ctx["fee"])
    inv = enroll(ctx).invoices.get(fee_type=ctx["fee"])
    l1, l2, _ = inv.lines.order_by("order")
    with pytest.raises(ValidationError):
        record_grouped_payment([(inv, D("9000"), [(l1, D("9000"))])])          # dépasse le poste
    with pytest.raises(ValidationError):
        record_grouped_payment([(inv, D("10000"), [(l1, D("8000"))])])        # somme différente
    assert not Payment.objects.exists() and not PaymentBatch.objects.exists()


def test_discount_reduces_the_first_line(ctx):
    from finance.services.discount_service import apply_enrollment_discount
    detail(ctx["fee"])
    e = enroll(ctx)
    apply_enrollment_discount(e, "fixed", 5000, "Fratrie")
    inv = e.invoices.get(fee_type=ctx["fee"])
    assert inv.total_amount == D("15000")
    assert [a for _, a, _ in lines_of(inv)] == [D("3000"), D("5000"), D("7000")]


def test_cancelled_payment_frees_the_lines(ctx):
    from administration.services.corrections import cancel_payment
    detail(ctx["fee"])
    inv = enroll(ctx).invoices.get(fee_type=ctx["fee"])
    p = Payment.objects.create(invoice=inv, amount=D("10000"))
    assert [p for _, _, p in lines_of(inv)] == [D("8000"), D("2000"), 0]
    cancel_payment(p, "erreur")
    assert [p for _, _, p in lines_of(inv)] == [0, 0, 0]


# ---------------------------------------------------------------- inscriptions existantes
def test_apply_to_existing_keeps_payments_and_asks_ventilation(ctx):
    paid_full, partial, unpaid = enroll(ctx, "A"), enroll(ctx, "B"), enroll(ctx, "C")
    inv_full = paid_full.invoices.get(fee_type=ctx["fee"])
    inv_part = partial.invoices.get(fee_type=ctx["fee"])
    p_full = Payment.objects.create(invoice=inv_full, amount=D("20000"))
    p_part = Payment.objects.create(invoice=inv_part, amount=D("12000"))
    receipts = {p_full.receipt_number, p_part.receipt_number}
    detail(ctx["fee"])
    assert not InvoiceLine.objects.exists()                     # rien tant qu'on n'a pas appliqué
    report = svc.apply_components_to_existing(ctx["fee"])
    assert report["created"] == 3 and report["to_ventilate"] == 1
    assert set(Payment.objects.values_list("receipt_number", flat=True)) == receipts
    assert [p for _, _, p in lines_of(inv_full)] == [D("8000"), D("5000"), D("7000")]   # soldée : ventilée d'office
    assert svc.unallocated(inv_part) == D("12000")
    assert [i.pk for i in svc.invoices_to_ventilate(fee=ctx["fee"])] == [inv_part.pk]
    l1, l2, l3 = inv_part.lines.order_by("order")
    svc.ventilate(inv_part, {l1: D("8000"), l3: D("4000")})
    assert svc.unallocated(inv_part) == 0
    assert [p for _, _, p in lines_of(inv_part)] == [D("8000"), 0, D("4000")]
    Payment.objects.get(pk=p_part.pk)                           # le paiement n'a pas bougé
    assert Payment.objects.get(pk=p_part.pk).amount == D("12000")


def test_apply_again_rebuilds_only_untouched_invoices(ctx):
    detail(ctx["fee"])
    a, b = enroll(ctx, "A"), enroll(ctx, "B")
    Payment.objects.create(invoice=a.invoices.get(fee_type=ctx["fee"]), amount=D("1000"))
    svc.save_components(ctx["fee"], [(None, "Frais d'inscription", D("10000")), (None, "Kit", D("10000"))])
    report = svc.apply_components_to_existing(ctx["fee"])
    assert report == {"created": 0, "rebuilt": 1, "kept": 1, "removed": 0, "to_ventilate": 0}
    assert [n for n, _, _ in lines_of(b.invoices.get(fee_type=ctx["fee"]))] == ["Frais d'inscription", "Kit"]


# ---------------------------------------------------------------- écrans
def test_screens_components_payment_and_ventilation(client, login, ctx):
    old = enroll(ctx, "Ancien")
    inv_old = old.invoices.get(fee_type=ctx["fee"])
    Payment.objects.create(invoice=inv_old, amount=D("6000"))
    login(Role.ADMIN)
    assert "Détailler en postes" in client.get("/finance/fees/").content.decode()
    r = client.post(f"/finance/fees/{ctx['fee'].id}/postes/", {"rows": "0", "name_0": "Frais d'inscription", "amount_0": "8000",
                                                               "name_1": "Manuel", "amount_1": "5 000", "name_2": "2 uniformes", "amount_2": "7000"})
    assert r.status_code == 302 and ctx["fee"].components.count() == 3
    client.post(f"/finance/fees/{ctx['fee'].id}/postes/", {"action": "apply"})
    page = client.get(f"/finance/fees/{ctx['fee'].id}/postes/").content.decode()
    assert f"/finance/factures/{inv_old.id}/ventilation/" in page
    # Fiche élève : postes et badge « À ventiler ».
    page = client.get(f"/students/{old.student_id}/").content.decode()
    assert "Manuel" in page and "À ventiler" in page
    l1, l2, l3 = inv_old.lines.order_by("order")
    r = client.post(f"/finance/factures/{inv_old.id}/ventilation/", {f"line_{l2.id}": "5000", f"line_{l3.id}": "1000"})
    assert r.status_code == 302 and svc.unallocated(inv_old) == 0
    # Encaissement : postes cochés.
    e = enroll(ctx, "Nouveau")
    inv = e.invoices.get(fee_type=ctx["fee"])
    n1, n2, n3 = inv.lines.order_by("order")
    page = client.get(f"/finance/encaissement/{e.id}/").content.decode()
    assert f'name="line_amount_{n2.id}"' in page
    assert client.get(f"/finance/invoices/{inv.id}/payment/").status_code == 302   # « Payer » → écran des postes
    r = client.post(f"/finance/encaissement/{e.id}/", {"invoice": [inv.id], f"amount_{inv.id}": "999",
                                                      "line": [n1.id, n2.id], f"line_amount_{n1.id}": "8000", f"line_amount_{n2.id}": "2000"})
    assert r.status_code == 302
    inv.refresh_from_db()
    assert inv.paid_amount == D("10000")
    assert [p for _, _, p in lines_of(inv)] == [D("8000"), D("2000"), 0]


def test_enrollment_form_pays_chosen_lines(client, login, ctx):
    detail(ctx["fee"])
    login(Role.ADMIN)
    fee = ctx["fee"]
    r = client.post("/enrollments/new/", {"first_name": "Binta", "last_name": "Sy", "sex": "F", "recruitment_year": "2026",
                                          "classe": ctx["classe"].id, "student_type": "regulier",
                                          "pay_fee": [fee.id], f"pay_amount_{fee.id}": "13000",
                                          f"pay_line_{fee.id}": ["0", "1"], f"pay_line_amount_{fee.id}_0": "8000",
                                          f"pay_line_amount_{fee.id}_1": "5000"})
    assert r.status_code == 302
    inv = Invoice.objects.get(enrollment__student__first_name="Binta", fee_type=fee)
    assert inv.paid_amount == D("13000") and [p for _, _, p in lines_of(inv)] == [D("8000"), D("5000"), 0]


def test_components_page_requires_finance_manage(client, login, ctx):
    login(Role.SECRETARY, username="secretaire")
    r = client.get(f"/finance/fees/{ctx['fee'].id}/postes/")
    assert r.status_code in (302, 403)
    assert not ctx["fee"].components.exists()


# ---------------------------------------------------------------- documents et annonces
def test_document_class_lists_its_students(client, login, ctx):
    enroll(ctx, "Kadia")
    login(Role.ADMIN)
    html = client.get(f"/documents/classes/{ctx['classe'].id}/students/").content.decode()
    assert "Diarra Kadia" in html
    page = client.get("/documents/add/").content.decode()
    assert "data-document-form" in page and "/documents/classes/0/students/" in page
    other = Classe.objects.create(school=ctx["classe"].school, school_year=ctx["year"], education_level=ctx["classe"].education_level, group="B", name="")
    assert "Aucun élève" in client.get(f"/documents/classes/{other.id}/students/").content.decode()


def test_published_announcement_can_be_corrected(client, login, ctx):
    from communication.models import Announcement
    a = Announcement.objects.create(title="Reunion des parant", message="Samedi")
    login(Role.ADMIN)
    assert f"/communication/{a.id}/modifier/" in client.get("/communication/").content.decode()
    form = client.get(f"/communication/{a.id}/modifier/")
    assert form.status_code == 200 and "Reunion des parant" in form.content.decode()
    r = client.post(f"/communication/{a.id}/modifier/", {"title": "Réunion des parents", "message": "Samedi à 9 h",
                                                         "audience": "PARENTS", "published_at": "2026-10-09T08:00", "is_active": "on"})
    assert r.status_code == 302
    a.refresh_from_db()
    assert a.title == "Réunion des parents" and a.updated_at is not None
    assert Announcement.objects.count() == 1


# ---------------------------------------------------------------- configuration initiale
def _setup_post(**extra):
    data = {"license_level": "1", "name": "École Test", "code": "ET", "currency": "FCFA",
            "school_year_start": "2026-10-01", "school_year_end": "2027-06-30"}
    for t, (reg, tui) in {"preschool": (20000, 60000), "fundamental_1": (5000, 90000), "fundamental_2": (5000, 100000)}.items():
        data[f"basefees-{t}_registration"] = str(reg)
        data[f"basefees-{t}_tuition"] = str(tui)
    data.update(extra)
    return data


def test_initial_configuration_can_detail_registration(client, login, db):
    from administration.models import School
    login(Role.ADMIN)
    page = client.get("/initial-configuration/").content.decode()
    assert "Détailler en postes" in page
    parts = {"basefees-preschool_part_name_0": "Frais d'inscription", "basefees-preschool_part_amount_0": "8000",
             "basefees-preschool_part_name_1": "Manuel", "basefees-preschool_part_amount_1": "5000",
             "basefees-preschool_part_name_2": "2 uniformes", "basefees-preschool_part_amount_2": "6000"}
    r = client.post("/initial-configuration/", _setup_post(**parts))
    assert r.status_code == 200 and "doit être égal au montant" in r.content.decode()   # 19 000 ≠ 20 000
    assert not School.objects.exists()
    parts["basefees-preschool_part_amount_2"] = "7000"
    r = client.post("/initial-configuration/", _setup_post(**parts))
    assert r.status_code == 302
    fee = FeeType.objects.get(name="Inscription", school_type="preschool")
    assert [(c.name, c.amount) for c in fee.components.all()] == [("Frais d'inscription", 8000), ("Manuel", 5000), ("2 uniformes", 7000)]
    assert fee.amount == D("20000")
    assert not FeeType.objects.get(name="Inscription", school_type="fundamental_1").components.exists()


# ---------------------------------------------------------------- listes par poste
def test_list_students_by_poste(client, login, ctx):
    detail(ctx["fee"])
    a, b, c = enroll(ctx, "Ali"), enroll(ctx, "Binta"), enroll(ctx, "Cheick")
    inv = lambda e: e.invoices.get(fee_type=ctx["fee"])
    lines = lambda e: list(inv(e).lines.order_by("order"))
    record_grouped_payment([(inv(a), D("15000"), [(lines(a)[0], D("8000")), (lines(a)[2], D("7000"))])])   # inscription + uniformes
    record_grouped_payment([(inv(b), D("11500"), [(lines(b)[0], D("8000")), (lines(b)[2], D("3500"))])])   # 1 uniforme sur 2
    uniformes = ctx["fee"].components.get(name="2 uniformes")
    login(Role.ADMIN)
    page = client.get("/finance/options/").content.decode()
    assert "Postes des frais détaillés" in page and f"option=p{uniformes.id}" in page
    r = client.get(f"/finance/options/?option=p{uniformes.id}&statut=solde")
    assert [row["student"].first_name for row in r.context["rows"]] == ["Ali"]
    r = client.get(f"/finance/options/?option=p{uniformes.id}&statut=partiel")
    assert [(row["student"].first_name, row["paid"]) for row in r.context["rows"]] == [("Binta", D("3500"))]
    r = client.get(f"/finance/options/?option=p{uniformes.id}&statut=rien")
    assert [row["student"].first_name for row in r.context["rows"]] == ["Cheick"]
    assert r.context["totals"]["total"] == D("7000")
    manuel = ctx["fee"].components.get(name="Manuel")
    r = client.get(f"/finance/options/?option=p{manuel.id}&statut=du")
    assert len(r.context["rows"]) == 3
    pdf = client.get(f"/finance/options/pdf/?option=p{uniformes.id}")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
