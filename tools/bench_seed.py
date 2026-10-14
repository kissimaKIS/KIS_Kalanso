"""Génère une base volumineuse pour mesurer les performances.

Usage : KIS_DATA_DIR=<dossier> python tools/bench_seed.py [nb_eleves]
Ne jamais lancer sur une vraie base : le script part d'une base vide.
"""
import datetime
import os
import random
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()

from django.db import transaction  # noqa: E402
from django.utils import timezone  # noqa: E402

from administration.models import (  # noqa: E402
    OtherPersonnel, Role, School, SchoolTypeActivation, SchoolYear, Teacher, User, UserRoleAssignment,
)
from communication.models import Announcement  # noqa: E402
from finance.models import FeeType, Invoice, Payment  # noqa: E402
from pedagogie.models import (  # noqa: E402
    BulletinItem, Classe, EducationLevel, Enrollment, Evaluation, Grade, Student, Teaching, Term,
)
from vie_scolaire.models import Attendance, TeacherAttendance  # noqa: E402

N_STUDENTS = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
random.seed(42)
FIRST = ["Awa", "Moussa", "Fanta", "Seydou", "Aminata", "Bakary", "Mariam", "Oumar", "Kadiatou", "Ibrahim", "Salif", "Djeneba"]
LAST = ["Traoré", "Diarra", "Coulibaly", "Keita", "Konaté", "Sidibé", "Cissé", "Touré", "Sangaré", "Dembélé", "Maïga", "Sissoko"]


@transaction.atomic
def main():
    admin = User.objects.create_superuser("admin", password="motdepasse1", first_name="Admin", last_name="KIS")
    admin.is_admin = True
    admin.save()
    school = School.objects.create(name="Complexe Scolaire Bench", code="CSB", school_type="fundamental_1", is_active=True)
    types = ["fundamental_1", "fundamental_2", "high_school"]
    for t in types:
        SchoolTypeActivation.objects.create(school=school, school_type=t, is_active=True)
    year = SchoolYear.objects.create(school=school, start_date=datetime.date(2026, 10, 1), end_date=datetime.date(2027, 6, 30), is_active=True)
    year.catalog_validated_at = timezone.now()
    year.save()

    levels = list(EducationLevel.objects.filter(school_type__in=types, is_active=True).order_by("school_type", "order"))
    classes = []
    for level in levels:
        for group in "ABCD":
            c = Classe(school=school, school_year=year, education_level=level, group=group, name="")
            c.save()
            classes.append(c)
    print(len(levels), "niveaux,", len(classes), "classes")

    terms = [Term.objects.create(school_year=year, name=f"Trimestre {i}", order=i) for i in (1, 2)]

    # Programme : 8 matières de bulletin par classe.
    class_subjects = {}
    items = []
    for c in classes:
        links = list(c.applicable_subject_links().filter(subject__is_active=True)[:8])
        class_subjects[c.id] = [l.subject_id for l in links]
        for i, l in enumerate(links):
            items.append(BulletinItem(classe=c, subject_id=l.subject_id, order=i + 1, max_score=10 if c.education_level.school_type == "fundamental_1" else 20))
    BulletinItem.objects.bulk_create(items)

    # Élèves et inscriptions
    students = [Student(first_name=random.choice(FIRST), last_name=random.choice(LAST), sex=random.choice("MF"),
                        matricule=f"M{i:06d}", date_of_birth=datetime.date(2012, 1, 1) + datetime.timedelta(days=i % 3000))
                for i in range(N_STUDENTS)]
    Student.objects.bulk_create(students, batch_size=1000)
    students = list(Student.objects.order_by("id"))
    enrollments = [Enrollment(student=s, classe=classes[i % len(classes)], school_year=year) for i, s in enumerate(students)]
    Enrollment.objects.bulk_create(enrollments, batch_size=1000)
    enrollments = list(Enrollment.objects.select_related("classe").order_by("id"))
    print(len(enrollments), "inscriptions")

    # Personnel
    teachers = [Teacher(employee_number=f"E{i:04d}", first_name=random.choice(FIRST), last_name=random.choice(LAST), phone="70000000",
                        pedagogical_profile="specialiste", monthly_salary=Decimal("150000")) for i in range(max(30, N_STUDENTS // 20))]
    Teacher.objects.bulk_create(teachers)
    teachers = list(Teacher.objects.all())
    OtherPersonnel.objects.bulk_create([OtherPersonnel(school=school, employee_number=f"P{i:04d}", first_name="Agent", last_name=str(i), function="Surveillant") for i in range(N_STUDENTS // 60)])
    teachings = []
    for c in classes:
        for j, sid in enumerate(class_subjects[c.id]):
            teachings.append(Teaching(teacher=teachers[(c.id * 3 + j) % len(teachers)], classe=c, subject_id=sid))
    Teaching.objects.bulk_create(teachings, ignore_conflicts=True)
    prof_user = User.objects.create_user("prof", password="motdepasse1")
    UserRoleAssignment.objects.create(user=prof_user, role=Role.TEACHER)
    teachers[0].user = prof_user
    teachers[0].save()
    for username, role in (("compta", Role.ACCOUNTANT), ("de", Role.STUDIES_DIRECTOR), ("secr", Role.SECRETARY)):
        u = User.objects.create_user(username, password="motdepasse1")
        UserRoleAssignment.objects.create(user=u, role=role)

    # Finance : 3 frais par élève, 2/3 payés partiellement
    fees = [FeeType.objects.create(name=n, category=cat, school_year=year, amount=Decimal(a), is_required=True)
            for n, cat, a in (("Inscription", "registration", 10000), ("Scolarité T1", "tuition", 50000), ("Scolarité T2", "tuition", 50000))]
    invoices = [Invoice(enrollment=e, fee_type=f, total_amount=f.amount) for e in enrollments for f in fees]
    Invoice.objects.bulk_create(invoices, batch_size=2000)
    invoices = list(Invoice.objects.all())
    payments = []
    for n, inv in enumerate(invoices):
        if n % 3:
            amount = inv.total_amount if n % 2 else inv.total_amount / 2
            payments.append(Payment(invoice=inv, amount=amount, receipt_number=f"R{n:07d}"))
            inv.paid_amount = amount
    Payment.objects.bulk_create(payments, batch_size=2000)
    Invoice.objects.bulk_update(invoices, ["paid_amount"], batch_size=2000)
    print(len(invoices), "factures,", len(payments), "paiements")

    # Notes : composition de période pour chaque matière, 2 trimestres
    grades = []
    for term in terms:
        evals = {c.id: Evaluation.objects.create(classe=c, term=term, name=f"Composition {term.order}", nature=Evaluation.Nature.PERIODIC_COMPOSITION, date=datetime.date(2026, 12, 15)) for c in classes}
        for e in enrollments:
            f1 = e.classe.education_level.school_type == "fundamental_1"
            for sid in class_subjects[e.classe_id]:
                grades.append(Grade(enrollment=e, subject_id=sid, term=term, evaluation=evals[e.classe_id],
                                    composition=round(random.uniform(3, 10 if f1 else 20), 2),
                                    class_average=None if f1 else round(random.uniform(5, 18), 2)))
                grades.append(Grade(enrollment=e, subject_id=sid, term=term,
                                    composition=round(random.uniform(3, 10 if f1 else 20), 2),
                                    class_average=None if f1 else round(random.uniform(5, 18), 2)))
    Grade.objects.bulk_create(grades, batch_size=5000)
    print(len(grades), "notes")

    # Présences : 20 jours
    days = [datetime.date(2026, 10, 5) + datetime.timedelta(days=d) for d in range(28) if (datetime.date(2026, 10, 5) + datetime.timedelta(days=d)).weekday() < 5]
    att = [Attendance(enrollment=e, date=d, status="PRESENT" if random.random() > 0.08 else "ABSENT") for d in days for e in enrollments]
    Attendance.objects.bulk_create(att, batch_size=5000)
    TeacherAttendance.objects.bulk_create([TeacherAttendance(teacher=t, school_year=year, date=d, status="PRESENT") for d in days for t in teachers], batch_size=5000)
    print(len(att), "présences")
    Announcement.objects.bulk_create([Announcement(title=f"Annonce {i}", message="Texte") for i in range(30)])


if __name__ == "__main__":
    main()
