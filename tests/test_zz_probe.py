import os
from decimal import Decimal
import pytest
from administration.models import Role, SchoolYear
from finance.models import FeeType, Invoice, Payment
from finance.services.options import add_option
from finance.services.arrears import add_prior_balance
from pedagogie.models import Classe, EducationLevel, Enrollment, Student

OUT = os.environ.get("KIS_APERCU")

@pytest.mark.skipif(not OUT, reason="aperçus uniquement")
def test_apercus(client, login, school):
    year = SchoolYear.objects.get(school=school); year.validate_catalog()
    lvl = EducationLevel.objects.get(code="LYC-10")
    a = Classe(school=school, school_year=year, education_level=lvl, group="A", name=""); a.save()
    scol = FeeType.objects.create(name="Scolarité", category="tuition", school_year=year, amount=Decimal("90000"), is_required=True)
    uni = FeeType.objects.create(name="Uniforme", category="optional", school_year=year, amount=Decimal("7500"), allows_quantity=True)
    kids = []
    for first, ph in (("Ali", "76413630"), ("Binta", "76413630"), ("Cheick", "76413630"), ("Djeneba", "70000000")):
        s = Student.objects.create(first_name=first, last_name="Diallo" if ph.startswith("76") else "Keita", father_name="Moussa Diallo" if ph.startswith("76") else "Sékou Keita", father_phone=ph)
        e = Enrollment.objects.create(student=s, classe=a, school_year=year); kids.append(e)
        add_option(e, uni, 2 if first != "Cheick" else 3, Decimal("8000"))
    Payment.objects.create(invoice=Invoice.objects.get(enrollment=kids[0], fee_type=scol), amount=Decimal("30000"))
    add_prior_balance(kids[0].student, school, 2024, Decimal("45000"))
    login(Role.ADMIN)
    for name, url in [("liste_uniforme.pdf", f"/finance/options/pdf/?option={uni.id}"),
                      ("liste_emargement.pdf", f"/finance/options/pdf/?option={uni.id}&montants=0"),
                      ("familles.pdf", "/finance/familles/pdf/"),
                      ("facture_famille.pdf", f"/finance/famille/{kids[0].id}/situation/")]:
        r = client.get(url); assert r.status_code == 200
        open(os.path.join(OUT, name), "wb").write(r.content)
    for name, url in [("familles.html", "/finance/familles/"), ("encaissement.html", f"/finance/encaissement/{kids[0].id}/?famille=1"),
                      ("fiche_eleve.html", f"/students/{kids[0].student.id}/"), ("correction.html", f"/corrections/changer-classe/{kids[0].id}/")]:
        r = client.get(url); assert r.status_code == 200, url
        open(os.path.join(OUT, name), "wb").write(r.content)
