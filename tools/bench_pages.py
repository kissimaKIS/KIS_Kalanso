"""Mesure temps et nombre de requêtes SQL des pages principales.

Usage : KIS_DATA_DIR=<dossier bench> python tools/bench_pages.py [utilisateur] [filtre]
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()
from django.conf import settings  # noqa: E402

settings.ALLOWED_HOSTS.append("testserver")
from django.db import connection, reset_queries  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402
from django.urls import reverse  # noqa: E402

import common.license_middleware as lm  # noqa: E402
lm.license_is_active = lambda: True

from administration.models import User  # noqa: E402
from finance.models import Payment  # noqa: E402
from pedagogie.models import Classe, Enrollment, Evaluation, Term  # noqa: E402

username = sys.argv[1] if len(sys.argv) > 1 else "admin"
only = sys.argv[2] if len(sys.argv) > 2 else ""
client = Client()
client.force_login(User.objects.get(username=username))
classe = Classe.objects.order_by("-id").first()  # une classe du secondaire
classe_f1 = Classe.objects.filter(education_level__school_type="fundamental_1").first()
term = Term.objects.order_by("order").first()
enr = Enrollment.objects.filter(classe=classe).first()
ev = Evaluation.objects.filter(classe=classe).first()
pay = Payment.objects.first()
pages = [
    ("dashboard", reverse("dashboard")),
    ("student_list", reverse("student_list")),
    ("classe_list", reverse("classe_list")),
    ("classe_detail", reverse("classe_detail", args=[classe.id])),
    ("student_detail", reverse("student_detail", args=[enr.student_id])),
    ("enrollment_create", reverse("enrollment_create")),
    ("teacher_list", reverse("teacher_list")),
    ("teaching_list", reverse("teaching_list")),
    ("term_list", reverse("term_list")),
    ("class_results", reverse("class_results", args=[classe.id, term.id])),
    ("class_results_f1", reverse("class_results", args=[classe_f1.id, term.id])),
    ("evaluation_results", reverse("evaluation_results", args=[ev.id])),
    ("class_bulletins", reverse("class_bulletins", args=[classe.id, term.id])),
    ("bulletin_pdf", reverse("bulletin_pdf", args=[enr.id, term.id])),
    ("class_bulletins_pdf", reverse("class_bulletins_pdf", args=[classe.id, term.id])),
    ("fee_type_list", reverse("fee_type_list")),
    ("invoice_list", reverse("invoice_list")),
    ("payment_list", reverse("payment_list")),
    ("payment_start", reverse("payment_start")),
    ("debt_report", reverse("debt_report")),
    ("debt_report_pdf", reverse("debt_report_pdf")),
    ("receipt_pdf", reverse("receipt_pdf", args=[pay.id])),
    ("invoice_statement_pdf", reverse("invoice_statement_pdf", args=[enr.id])),
    ("attendance_list", reverse("attendance_list")),
    ("attendance_list_classe", reverse("attendance_list") + f"?classe={classe.id}"),
    ("student_list_page40", reverse("student_list") + "?page=40"),
    ("invoice_list_unpaid", reverse("invoice_list") + "?status=unpaid&page=20"),
    ("attendance_mark", reverse("attendance_mark", args=[classe.id])),
    ("staff_attendance_list", reverse("staff_attendance_list")),
    ("discipline_list", reverse("discipline_list")),
    ("student_list_pdf", reverse("student_list_pdf")),
    ("cartes_identite_classe_pdf", reverse("cartes_identite_classe_pdf", args=[classe.id])),
    ("teacher_payment_list", reverse("teacher_payment_list")),
    ("permanent_annual_statement", reverse("permanent_annual_statement")),
    ("budget_list", reverse("budget_list")),
    ("announcement_list", reverse("announcement_list")),
    ("user_list", reverse("user_list")),
    ("passage_list", reverse("passage_list")),
]
print(f"{'page':30} {'ms':>8} {'requêtes':>9} {'Ko':>8}  statut")
total = 0
for name, url in pages:
    if only and only not in name:
        continue
    reset_queries()
    with CaptureQueriesContext(connection) as ctx:
        t = time.perf_counter()
        r = client.get(url)
        ms = (time.perf_counter() - t) * 1000
    total += ms
    size = len(r.content) // 1024 if not getattr(r, "streaming", False) else 0
    print(f"{name:30} {ms:8.0f} {len(ctx.captured_queries):9d} {size:8d}  {r.status_code}")
print(f"{'TOTAL':30} {total:8.0f}")
