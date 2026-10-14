import datetime

import pytest

from administration.models import Role, School, SchoolYear, Teacher, User, UserRoleAssignment


@pytest.fixture(autouse=True)
def _license_ok(monkeypatch):
    """La licence n'est pas l'objet de ces tests."""
    import common.license_middleware as lm
    monkeypatch.setattr(lm, "license_is_active", lambda: True, raising=False)


@pytest.fixture
def school(db):
    school = School.objects.create(name="Lycée Test", code="LT", school_type=School.SchoolType.HIGH_SCHOOL, is_active=True)
    SchoolYear.objects.create(school=school, start_date=datetime.date(2026, 10, 1), end_date=datetime.date(2027, 6, 30), is_active=True)
    return school


@pytest.fixture
def make_user(db):
    def _make(username, *roles, superuser=False):
        if superuser:
            user = User.objects.create_superuser(username=username, password="motdepasse1")
        else:
            user = User.objects.create_user(username=username, password="motdepasse1")
        for role in roles:
            UserRoleAssignment.objects.create(user=user, role=role)
        return user
    return _make


@pytest.fixture
def login(client, make_user):
    def _login(*roles, username=None, superuser=False):
        user = make_user(username or "u_" + "_".join(str(r).lower() for r in roles) or "admin", *roles, superuser=superuser)
        client.force_login(user)
        return user
    return _login


@pytest.fixture
def teacher(db):
    return Teacher.objects.create(employee_number="T001", first_name="Awa", last_name="Diarra", phone="70000000",
                                  pedagogical_profile=Teacher.PedagogicalProfile.SPECIALISTE)


@pytest.fixture(autouse=True)
def _fast_password_hasher(settings):
    """PBKDF2 (1 M itérations) est volontairement lent : inutile en test."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def build_complex(n_students=40, n_classes=4, school_types=("fundamental_1", "fundamental_2")):
    """Petit complexe scolaire réaliste (notes, factures, paiements, présences)."""
    import random
    from decimal import Decimal

    from django.utils import timezone

    from administration.models import SchoolTypeActivation
    from finance.models import FeeType, Invoice, Payment
    from pedagogie.models import BulletinItem, Classe, EducationLevel, Enrollment, Grade, Student, Teaching, Term
    from vie_scolaire.models import Attendance

    rnd = random.Random(7)
    school = School.objects.create(name="Complexe", code="CX", school_type=school_types[0], is_active=True)
    for t in school_types:
        SchoolTypeActivation.objects.create(school=school, school_type=t, is_active=True)
    year = SchoolYear.objects.create(school=school, start_date=datetime.date(2026, 10, 1), end_date=datetime.date(2027, 6, 30), is_active=True)
    year.catalog_validated_at = timezone.now()
    year.save()
    levels = list(EducationLevel.objects.filter(school_type__in=school_types, is_active=True).order_by("school_type", "order"))
    classes = []
    for i in range(n_classes):
        classe = Classe(school=school, school_year=year, education_level=levels[i % len(levels)], group="ABCDEFGH"[i // len(levels)], name="")
        classe.save()
        classes.append(classe)
    term = Term.objects.create(school_year=year, name="Trimestre 1", order=1)
    subjects = {}
    for classe in classes:
        links = list(classe.applicable_subject_links().filter(subject__is_active=True)[:5])
        subjects[classe.id] = [link.subject_id for link in links]
        BulletinItem.objects.bulk_create([
            BulletinItem(classe=classe, subject_id=link.subject_id, order=n + 1, coefficient=link.coefficient or 1,
                         max_score=10 if classe.education_level.school_type == "fundamental_1" else 20)
            for n, link in enumerate(links)
        ])
        BulletinItem.objects.create(classe=classe, label="Conduite", order=99,
                                    max_score=10 if classe.education_level.school_type == "fundamental_1" else 20)
    Student.objects.bulk_create([Student(first_name=f"Prénom{i}", last_name=f"Nom{i % 9}", sex="MF"[i % 2], matricule=f"MAT{i:05d}") for i in range(n_students)])
    students = list(Student.objects.order_by("id"))
    Enrollment.objects.bulk_create([Enrollment(student=s, classe=classes[i % n_classes], school_year=year) for i, s in enumerate(students)])
    enrollments = list(Enrollment.objects.select_related("classe__education_level").order_by("id"))
    grades = []
    for e in enrollments:
        f1 = e.classe.education_level.school_type == "fundamental_1"
        for sid in subjects[e.classe_id]:
            if rnd.random() < 0.1:
                continue  # notes manquantes : le calcul doit les ignorer
            grades.append(Grade(enrollment=e, subject_id=sid, term=term, composition=round(rnd.uniform(2, 10 if f1 else 20), 2),
                                class_average=None if f1 else round(rnd.uniform(4, 18), 2)))
    Grade.objects.bulk_create(grades)
    from pedagogie.models import BulletinItemResult
    custom = {item.classe_id: item for item in BulletinItem.objects.filter(subject__isnull=True)}
    results = []
    for e in enrollments:
        item = custom[e.classe_id]
        if e.classe.education_level.school_type == "fundamental_1":
            results.append(BulletinItemResult(enrollment=e, bulletin_item=item, term=term, note=rnd.randint(3, 10)))
        else:
            results.append(BulletinItemResult(enrollment=e, bulletin_item=item, term=term, composition=rnd.randint(3, 20), class_average=rnd.randint(3, 20)))
    BulletinItemResult.objects.bulk_create(results)
    fee = FeeType.objects.create(name="Scolarité", category="tuition", school_year=year, amount=Decimal("30000"))
    Invoice.objects.bulk_create([Invoice(enrollment=e, fee_type=fee, total_amount=fee.amount, paid_amount=Decimal("10000") if i % 2 else 0) for i, e in enumerate(enrollments)])
    Payment.objects.bulk_create([Payment(invoice=inv, amount=Decimal("10000"), receipt_number=f"R{inv.id}") for inv in Invoice.objects.filter(paid_amount__gt=0)])
    Attendance.objects.bulk_create([Attendance(enrollment=e, date=datetime.date(2026, 10, 5) + datetime.timedelta(days=d), status="PRESENT") for d in range(3) for e in enrollments])
    teacher = Teacher.objects.create(employee_number="T9", first_name="Prof", last_name="Test", phone="1", pedagogical_profile="specialiste")
    Teaching.objects.bulk_create([Teaching(teacher=teacher, classe=c, subject_id=subjects[c.id][0]) for c in classes])
    return {"school": school, "year": year, "classes": classes, "term": term, "enrollments": enrollments}
