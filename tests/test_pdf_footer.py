"""V5-9 : « Document généré par KIS Kalanso » en pied de page, à gauche (plus dans le corps)."""
import io
from decimal import Decimal

import pytest
from pypdf import PdfReader

from administration.models import Role, SchoolYear
from finance.models import FeeType, Invoice, Payment
from pedagogie.models import Classe, EducationLevel, Enrollment, Student


class _Collector:
    def __init__(self):
        self.items = []

    def __call__(self, text, cm, tm, font_dict, font_size):
        if text.strip():
            self.items.append((text.strip(), tm[5] if tm else None, tm[4] if tm else None))


def test_mention_is_in_footer_on_the_left(client, login, school):
    year = SchoolYear.objects.get(school=school)
    year.validate_catalog()
    classe = Classe(school=school, school_year=year, education_level=EducationLevel.objects.get(code="LYC-10"), group="A", name="")
    classe.save()
    fee = FeeType.objects.create(name="Inscription", category="registration", school_year=year, amount=Decimal("10000"), is_required=True)
    e = Enrollment.objects.create(student=Student.objects.create(first_name="Ali", last_name="Diallo"), classe=classe, school_year=year)
    p = Payment.objects.create(invoice=Invoice.objects.get(enrollment=e, fee_type=fee), amount=Decimal("10000"))
    login(Role.ADMIN)
    pdf = client.get(f"/finance/payments/{p.id}/receipt/").content
    page = PdfReader(io.BytesIO(pdf)).pages[0]
    collector = _Collector()
    page.extract_text(visitor_text=collector)
    hits = [(y, x) for text, y, x in collector.items if "Document généré par KIS Kalanso" in text]
    assert len(hits) == 1, collector.items
    y, x = hits[0]
    assert y < 30 and x < 80   # bas de page (7 mm), marge de gauche
