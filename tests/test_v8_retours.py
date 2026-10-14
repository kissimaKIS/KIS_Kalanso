"""Retours V8 (13/10) : documents filtrés, pièces du dossier à l'inscription, suppression
d'un document, recettes scolaires regroupées dans le budget, reçus en 2 exemplaires,
molette désactivée sur les champs numériques."""
import datetime
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from administration.models import Role, SchoolYear
from documents.models import Document
from finance.models import FeeType, Invoice, Payment
from finance.services.grouped_payment import record_grouped_payment
from pedagogie.models import Classe, EducationLevel, Enrollment, Student

D = Decimal


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def ctx(school):
    year = SchoolYear.objects.get(school=school)
    year.validate_catalog()
    lvl = EducationLevel.objects.get(code="LYC-10")
    a = Classe(school=school, school_year=year, education_level=lvl, group="A", name=""); a.save()
    b = Classe(school=school, school_year=year, education_level=lvl, group="B", name=""); b.save()
    insc = FeeType.objects.create(name="Inscription", category="registration", school_year=year, amount=D("10000"), is_required=True)
    scol = FeeType.objects.create(name="Scolarité", category="tuition", school_year=year, amount=D("90000"), is_required=True)
    ali = Student.objects.create(first_name="Ali", last_name="Diallo", sex="M")
    binta = Student.objects.create(first_name="Binta", last_name="Keita", sex="F")
    ea = Enrollment.objects.create(student=ali, classe=a, school_year=year)
    eb = Enrollment.objects.create(student=binta, classe=b, school_year=year)
    return dict(year=year, a=a, b=b, insc=insc, scol=scol, ali=ali, binta=binta, ea=ea, eb=eb)


def pdf_file(name="acte.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 test", content_type="application/pdf")


# ---------------------------------------------------------------- 1. filtres
def test_documents_filtered_by_category_then_class(client, login, ctx):
    Document.objects.create(title="Acte de naissance", category="STUDENT", file=pdf_file(), student=ctx["ali"], classe=ctx["a"])
    Document.objects.create(title="Vaccination", category="STUDENT", file=pdf_file("v.pdf"), student=ctx["binta"])  # sans classe
    Document.objects.create(title="Règlement intérieur", category="ADMIN", file=pdf_file("r.pdf"))
    login(Role.ADMIN)
    page = client.get("/documents/?categorie=ADMIN")
    assert [d.title for d in page.context["documents"]] == ["Règlement intérieur"]
    page = client.get("/documents/?categorie=STUDENT")
    assert "Toutes les classes" in page.content.decode()
    page = client.get(f"/documents/?categorie=STUDENT&classe={ctx['b'].id}")
    assert [d.title for d in page.context["documents"]] == ["Vaccination"]       # retrouvé par l'inscription de l'élève
    page = client.get("/documents/?q=diallo")
    assert [d.title for d in page.context["documents"]] == ["Acte de naissance"]


# ---------------------------------------------------------------- 2. pièces à l'inscription
def test_enrollment_with_pieces_and_student_card(client, login, ctx):
    login(Role.SECRETARY)
    r = client.get("/enrollments/new/")
    assert "Pièces du dossier" in r.content.decode() and "Certificat de vaccination" in r.content.decode()
    r = client.post("/enrollments/new/", {"first_name": "Coumba", "last_name": "Sy", "sex": "F", "recruitment_year": "2026",
                                          "classe": ctx["a"].id, "student_type": "regulier",
                                          "piece_type_0": "Acte de naissance", "piece_file_0": pdf_file(),
                                          "piece_type_1": "", "piece_title_1": "Lettre du médecin", "piece_file_1": pdf_file("m.pdf"),
                                          "piece_type_2": "Carnet de santé"})                                  # sans fichier : ignorée
    assert r.status_code == 302
    student = Student.objects.get(first_name="Coumba")
    assert sorted(student.documents.values_list("title", flat=True)) == ["Acte de naissance", "Lettre du médecin"]
    assert set(student.documents.values_list("category", flat=True)) == {"STUDENT"}
    page = client.get(f"/students/{student.id}/").content.decode()
    assert "Pièces du dossier" in page and "Lettre du médecin" in page
    form = client.get(f"/documents/add/?student={student.id}")
    assert form.status_code == 200 and form.context["form"].initial["classe"] == ctx["a"].id
    r = client.post(f"/documents/add/?student={student.id}", {"title": "Certificat de vaccination", "category": "STUDENT",
                                                              "classe": ctx["a"].id, "student": student.id, "file": pdf_file("c.pdf"),
                                                              "next": f"/students/{student.id}/"})
    assert r.status_code == 302 and r["Location"] == f"/students/{student.id}/"
    assert student.documents.count() == 3


# ---------------------------------------------------------------- 3. suppression
def test_delete_document_removes_file(client, login, ctx):
    doc = Document.objects.create(title="Erreur", category="STUDENT", file=pdf_file(), student=ctx["ali"])
    storage, name = doc.file.storage, doc.file.name
    assert storage.exists(name)
    login(Role.SECRETARY)
    assert "Supprimer définitivement" in client.get(f"/documents/{doc.id}/delete/").content.decode()
    r = client.post(f"/documents/{doc.id}/delete/", {"next": f"/students/{ctx['ali'].id}/"})
    assert r.status_code == 302 and r["Location"] == f"/students/{ctx['ali'].id}/"
    assert not Document.objects.exists() and not storage.exists(name)
    doc = Document.objects.create(title="X", category="OTHER", file=pdf_file())
    r = client.post(f"/documents/{doc.id}/delete/", {"next": "https://exemple.com/"})
    assert r["Location"] == "/documents/"                                           # pas de redirection externe


# ---------------------------------------------------------------- 4. budget
def test_budget_groups_school_receipts_by_day_and_type(client, login, ctx):
    inv = lambda e, f: Invoice.objects.get(enrollment=e, fee_type=f)
    record_grouped_payment([(inv(ctx["ea"], ctx["insc"]), D("10000")), (inv(ctx["ea"], ctx["scol"]), D("30000"))])
    record_grouped_payment([(inv(ctx["eb"], ctx["insc"]), D("10000")), (inv(ctx["eb"], ctx["scol"]), D("20000"))])
    old = Payment.objects.create(invoice=inv(ctx["eb"], ctx["scol"]), amount=D("5000"))
    Payment.objects.filter(pk=old.pk).update(date=datetime.date.today() - datetime.timedelta(days=3))
    login(Role.ADMIN)
    r = client.get("/budget/")
    ops = list(r.context["operations"])
    assert [(o["label"].split(" — ")[1], o["amount"]) for o in ops] == [
        ("Frais d'inscription (2 versements)", D("20000")), ("Scolarité (2 versements)", D("50000")), ("Scolarité (1 versement)", D("5000"))]
    assert {t["label"]: t["amount"] for t in r.context["school_totals"]} == {"Frais d'inscription": D("20000"), "Scolarité": D("55000")}
    assert r.context["revenue"] == D("75000")
    r = client.get("/budget/?category=school:registration")
    assert r.context["revenue"] == D("20000") and len(list(r.context["operations"])) == 1
    for url in ("/budget/pdf/?category=school:tuition", "/budget/cash-pdf/"):
        pdf = client.get(url)
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


# ---------------------------------------------------------------- 5. molette
def test_mouse_wheel_does_not_change_numbers(client, login, ctx):
    from django.contrib.staticfiles import finders
    js = open(finders.find("js/app.js"), encoding="utf-8").read()
    assert "'wheel'" in js and "el.blur()" in js


# ---------------------------------------------------------------- 7. reçus côte à côte
def test_receipt_two_copies_on_one_landscape_page(client, login, ctx):
    from io import BytesIO
    from pypdf import PdfReader
    batch = record_grouped_payment([(Invoice.objects.get(enrollment=ctx["ea"], fee_type=ctx["insc"]), D("10000"))])
    single = Payment.objects.create(invoice=Invoice.objects.get(enrollment=ctx["eb"], fee_type=ctx["insc"]), amount=D("4000"))
    login(Role.ADMIN)
    for url in (f"/finance/recus/{batch.id}/?exemplaires=2", f"/finance/payments/{single.id}/receipt/?exemplaires=2"):
        reader = PdfReader(BytesIO(client.get(url).content))
        assert len(reader.pages) == 1
        page = reader.pages[0]
        assert float(page.mediabox.width) > float(page.mediabox.height)          # A4 paysage
        text = page.extract_text()
        assert text.count("REÇU DE PAIEMENT") == 2 and "Exemplaire parent" in text and "Exemplaire établissement" in text
    done = client.get(f"/finance/encaissement/termine/?batch={batch.id}").content.decode()
    assert "?exemplaires=2" in done


def test_several_receipts_two_per_page(client, login, ctx):
    from io import BytesIO
    from pypdf import PdfReader
    inv = lambda e, f: Invoice.objects.get(enrollment=e, fee_type=f)
    b1 = record_grouped_payment([(inv(ctx["ea"], ctx["insc"]), D("10000")), (inv(ctx["ea"], ctx["scol"]), D("5000"))])
    b2 = record_grouped_payment([(inv(ctx["eb"], ctx["insc"]), D("10000"))])
    single = Payment.objects.create(invoice=inv(ctx["eb"], ctx["scol"]), amount=D("4000"))
    login(Role.ADMIN)
    page = client.get("/finance/payments/").content.decode()
    assert f'value="b{b1.id}"' in page and f'value="p{single.id}"' in page and "Reçus cochés" in page
    r = client.get(f"/finance/recus/imprimer/?recu=b{b1.id}&recu=b{b1.id}&recu=b{b2.id}&recu=p{single.id}")
    reader = PdfReader(BytesIO(r.content))
    assert len(reader.pages) == 2                                                   # 3 reçus → 2 feuilles
    texts = [p.extract_text() for p in reader.pages]
    assert texts[0].count("REÇU DE PAIEMENT") == 2 and texts[1].count("REÇU DE PAIEMENT") == 1
    assert b1.receipt_number in texts[0] and b2.receipt_number in texts[0] and single.receipt_number in texts[1]
    r = client.get(f"/finance/recus/imprimer/?date={datetime.date.today().isoformat()}")
    assert len(PdfReader(BytesIO(r.content)).pages) == 2
    assert client.get("/finance/recus/imprimer/?date=2000-01-01").status_code == 404
