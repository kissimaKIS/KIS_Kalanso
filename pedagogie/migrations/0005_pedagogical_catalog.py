from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


LEVELS = [
    # code, name, school_type, order, exam, allows_free_candidate
    ("PS", "Petite Section", "preschool", 1, "", False),
    ("MS", "Moyenne Section", "preschool", 2, "", False),
    ("GS", "Grande Section", "preschool", 3, "", False),
    ("F1-1", "1ère année", "fundamental_1", 1, "", False),
    ("F1-2", "2ème année", "fundamental_1", 2, "", False),
    ("F1-3", "3ème année", "fundamental_1", 3, "", False),
    ("F1-4", "4ème année", "fundamental_1", 4, "", False),
    ("F1-5", "5ème année", "fundamental_1", 5, "", False),
    ("F1-6", "6ème année", "fundamental_1", 6, "", False),
    ("F2-7", "7ème année", "fundamental_2", 1, "", False),
    ("F2-8", "8ème année", "fundamental_2", 2, "", False),
    ("F2-9", "9ème année", "fundamental_2", 3, "DEF", True),
    ("LYC-10", "10ème année", "high_school", 1, "", False),
    ("LYC-11", "11ème année", "high_school", 2, "", False),
    ("LYC-12", "12ème année", "high_school", 3, "BAC", True),
    ("CAP-1", "CAP 1", "vocational", 1, "", False),
    ("CAP-2", "CAP 2", "vocational", 2, "CAP", True),
    ("BT-1", "BT 1", "vocational", 3, "BT1", True),
    ("BT-2", "BT 2", "vocational", 4, "BT2", True),
]

SUBJECTS = [
    ("FR", "Français"),
    ("MATH", "Mathématiques"),
    ("SCI", "Sciences"),
    ("HG", "Histoire-Géographie"),
    ("ANG", "Anglais"),
    ("ECM", "Éducation civique et morale"),
    ("EPS", "Éducation physique et sportive"),
    ("ART", "Arts / Activités artistiques"),
    ("PHCH", "Physique-Chimie"),
    ("SVT", "Sciences de la Vie et de la Terre"),
    ("PHILO", "Philosophie"),
    ("INFO", "Informatique"),
    ("TECH", "Enseignement technique"),
    ("PRO", "Pratique professionnelle"),
]


F1_SUBJECTS = ["FR", "MATH", "SCI", "HG", "ECM", "EPS", "ART"]
F2_SUBJECTS = ["FR", "MATH", "SCI", "HG", "ANG", "ECM", "EPS"]
LYC_SUBJECTS = ["FR", "MATH", "ANG", "HG", "PHCH", "SVT", "EPS", "INFO"]
PRO_SUBJECTS = ["FR", "MATH", "ANG", "INFO", "TECH", "PRO", "EPS"]


def populate_subject_codes(apps, schema_editor):
    Subject = apps.get_model("pedagogie", "Subject")
    for subject in Subject.objects.filter(code__isnull=True):
        subject.code = f"SUB-{subject.pk}"
        subject.save(update_fields=["code"])


def seed_catalog(apps, schema_editor):
    EducationLevel = apps.get_model("pedagogie", "EducationLevel")
    Subject = apps.get_model("pedagogie", "Subject")
    EducationLevelSubject = apps.get_model("pedagogie", "EducationLevelSubject")
    EvaluationRule = apps.get_model("pedagogie", "EvaluationRule")
    School = apps.get_model("administration", "School")
    SchoolYear = apps.get_model("administration", "SchoolYear")
    SchoolYearLevel = apps.get_model("pedagogie", "SchoolYearLevel")

    levels = {}
    for code, name, school_type, order, exam_name, free_candidate in LEVELS:
        level, _ = EducationLevel.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "school_type": school_type,
                "order": order,
                "is_exam_level": bool(exam_name),
                "exam_name": exam_name,
                "allows_free_candidate": free_candidate,
                "is_active": True,
            },
        )
        levels[code] = level

    subjects = {}
    for code, name in SUBJECTS:
        subject = Subject.objects.filter(code=code).first()
        if subject is None:
            subject = Subject.objects.filter(name=name).first()
        if subject is None:
            subject = Subject.objects.create(code=code, name=name, coefficient=1, is_active=True)
        elif not subject.code:
            subject.code = code
            subject.save(update_fields=["code"])
        subjects[code] = subject

    for level_code, codes in [(c, []) for c, *_ in LEVELS]:
        if level_code.startswith("F1-"):
            codes = F1_SUBJECTS
        elif level_code.startswith("F2-"):
            codes = F2_SUBJECTS
        elif level_code.startswith("LYC-"):
            codes = LYC_SUBJECTS
            if level_code == "LYC-10":
                codes = [c for c in codes if c != "PHILO"]
        elif level_code.startswith("CAP-") or level_code.startswith("BT-"):
            codes = PRO_SUBJECTS
        else:
            codes = []
        for order, subject_code in enumerate(codes, 1):
            EducationLevelSubject.objects.get_or_create(
                education_level=levels[level_code],
                subject=subjects[subject_code],
                defaults={"coefficient": 1, "order": order, "is_active": True},
            )

    # Les règles initiales correspondent au fonctionnement actuel du MVP :
    # devoir + composition pondérée 1/3 + 2/3. Elles restent dans le référentiel
    # afin que le moteur d'évaluation puisse évoluer sans recoder les niveaux.
    for level in levels.values():
        if level.school_type == "preschool":
            EvaluationRule.objects.get_or_create(
                education_level=level,
                code="OBSERVATION",
                defaults={"label": "Observation", "weight": Decimal("1"), "max_score": Decimal("20"), "order": 1, "is_required": False, "is_active": True},
            )
        else:
            EvaluationRule.objects.get_or_create(
                education_level=level,
                code="DEVOIR",
                defaults={"label": "Devoir", "weight": Decimal("1"), "max_score": Decimal("20"), "order": 1, "is_required": False, "is_active": True},
            )
            EvaluationRule.objects.get_or_create(
                education_level=level,
                code="COMPOSITION",
                defaults={"label": "Composition", "weight": Decimal("2"), "max_score": Decimal("20"), "order": 2, "is_required": False, "is_active": True},
            )

    # Toute nouvelle année scolaire reçoit automatiquement les niveaux du
    # référentiel correspondant au type de l'établissement.
    for year in SchoolYear.objects.select_related("school").all():
        valid_levels = EducationLevel.objects.filter(school_type=year.school.school_type, is_active=True)
        SchoolYearLevel.objects.bulk_create(
            [SchoolYearLevel(school_year=year, education_level=level, is_active=True) for level in valid_levels],
            ignore_conflicts=True,
        )


def migrate_old_classes(apps, schema_editor):
    Classe = apps.get_model("pedagogie", "Classe")
    EducationLevel = apps.get_model("pedagogie", "EducationLevel")

    for classe in Classe.objects.select_related("school").all():
        level = classe.level
        school_type = classe.school.school_type
        code = None
        if school_type == "fundamental_1" and 1 <= level <= 6:
            code = f"F1-{level}"
        elif school_type == "fundamental_2" and 7 <= level <= 9:
            code = f"F2-{level}"
        elif school_type == "high_school" and 10 <= level <= 12:
            code = f"LYC-{level}"
        elif school_type == "vocational":
            code = {1: "CAP-1", 2: "CAP-2", 3: "BT-1", 4: "BT-2"}.get(level)
        if code:
            level_obj = EducationLevel.objects.filter(code=code).first()
            if level_obj:
                classe.education_level_id = level_obj.id
                classe.save(update_fields=["education_level"])


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("administration", "0004_school_type_and_schoolyear_school"),
        ("pedagogie", "0004_student_sex"),
    ]

    operations = [
        migrations.CreateModel(
            name="EducationLevel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=30, unique=True, verbose_name="Code")),
                ("name", models.CharField(max_length=100, verbose_name="Niveau")),
                ("school_type", models.CharField(choices=[("preschool", "Préscolaire"), ("fundamental_1", "Fondamentale 1"), ("fundamental_2", "Fondamentale 2"), ("high_school", "Lycée"), ("vocational", "Centre professionnel")], max_length=30, verbose_name="Type d'établissement")),
                ("order", models.PositiveSmallIntegerField(default=1, verbose_name="Ordre")),
                ("is_exam_level", models.BooleanField(default=False, verbose_name="Classe d'examen")),
                ("exam_name", models.CharField(blank=True, max_length=50, verbose_name="Examen")),
                ("allows_free_candidate", models.BooleanField(default=False, verbose_name="Autorise candidat libre")),
                ("is_active", models.BooleanField(default=True, verbose_name="Actif")),
            ],
            options={"ordering": ["school_type", "order", "id"], "verbose_name": "Niveau pédagogique", "verbose_name_plural": "Niveaux pédagogiques"},
        ),
        migrations.CreateModel(
            name="SchoolYearLevel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_active", models.BooleanField(default=True, verbose_name="Ouvert dans l'établissement")),
                ("education_level", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="school_year_configurations", to="pedagogie.educationlevel")),
                ("school_year", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="configured_levels", to="administration.schoolyear")),
            ],
            options={"ordering": ["education_level__order"], "verbose_name": "Niveau de l'année scolaire", "verbose_name_plural": "Niveaux de l'année scolaire"},
        ),
        migrations.CreateModel(
            name="EducationLevelSubject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("coefficient", models.PositiveIntegerField(default=1, verbose_name="Coefficient")),
                ("order", models.PositiveSmallIntegerField(default=1, verbose_name="Ordre")),
                ("is_active", models.BooleanField(default=True, verbose_name="Active")),
                ("education_level", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="subject_links", to="pedagogie.educationlevel")),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="level_links", to="pedagogie.subject")),
            ],
            options={"ordering": ["order", "subject__name"], "verbose_name": "Matière par niveau", "verbose_name_plural": "Matières par niveau"},
        ),
        migrations.CreateModel(
            name="EvaluationRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=30)),
                ("label", models.CharField(max_length=100)),
                ("weight", models.DecimalField(decimal_places=2, default=1, max_digits=6)),
                ("max_score", models.DecimalField(decimal_places=2, default=20, max_digits=6)),
                ("order", models.PositiveSmallIntegerField(default=1)),
                ("is_required", models.BooleanField(default=True)),
                ("is_active", models.BooleanField(default=True)),
                ("education_level", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="evaluation_rules", to="pedagogie.educationlevel")),
            ],
            options={"ordering": ["education_level__order", "order", "id"], "verbose_name": "Règle d'évaluation", "verbose_name_plural": "Règles d'évaluation"},
        ),
        migrations.AddField(
            model_name="classe",
            name="education_level",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="classes", to="pedagogie.educationlevel", verbose_name="Niveau"),
        ),
        migrations.AddField(model_name="subject", name="code", field=models.CharField(max_length=30, null=True, unique=True, verbose_name="Code")),
        migrations.AddField(model_name="subject", name="is_active", field=models.BooleanField(default=True, verbose_name="Active")),
        migrations.RunPython(populate_subject_codes, reverse_noop),
        migrations.AlterField(
            model_name="subject",
            name="code",
            field=models.CharField(max_length=30, unique=True, verbose_name="Code"),
        ),
        migrations.RunPython(seed_catalog, reverse_noop),
        migrations.RunPython(migrate_old_classes, reverse_noop),
        migrations.AlterField(
            model_name="classe",
            name="education_level",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="classes", to="pedagogie.educationlevel", verbose_name="Niveau"),
        ),
        migrations.AddConstraint(model_name="educationlevel", constraint=models.UniqueConstraint(fields=("school_type", "order"), name="unique_level_order_per_school_type")),
        migrations.AddConstraint(model_name="schoolyearlevel", constraint=models.UniqueConstraint(fields=("school_year", "education_level"), name="unique_school_year_level")),
        migrations.AddConstraint(model_name="educationlevelsubject", constraint=models.UniqueConstraint(fields=("education_level", "subject"), name="unique_subject_per_level")),
        migrations.AddConstraint(model_name="evaluationrule", constraint=models.UniqueConstraint(fields=("education_level", "code"), name="unique_evaluation_rule_per_level")),
    ]
