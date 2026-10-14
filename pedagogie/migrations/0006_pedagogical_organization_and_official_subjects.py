from django.db import migrations, models
import django.db.models.deletion


OFFICIAL_SUBJECTS = [
    ("FR", "Français"),
    ("MATH", "Mathématiques"),
    ("SCI_OBS", "Sciences d'observation"),
    ("ECM", "Éducation civique et morale"),
    ("EPS", "Éducation physique et sportive"),
    ("DRAW", "Dessin"),
    ("MUSIC", "Éducation musicale"),
    ("ART_ED", "Éducation artistique"),
    ("TECH", "Technologie"),
    ("EF", "Économie familiale"),
    ("HIST", "Histoire"),
    ("GEO", "Géographie"),
    ("ANG", "Anglais"),
    ("SCI_NAT", "Sciences naturelles"),
    ("SCI_PHY", "Sciences physiques"),
    ("ACT_RUR", "Activités pratiques et ruralisation"),
]


F1_MAPPING = {
    1: ["FR", "MATH", "SCI_OBS", "ECM", "EPS", "DRAW", "MUSIC", "ART_ED", "TECH"],
    2: ["FR", "MATH", "SCI_OBS", "ECM", "EPS", "DRAW", "MUSIC", "ART_ED", "TECH"],
    3: ["FR", "MATH", "SCI_OBS", "ECM", "EPS", "DRAW", "MUSIC", "ART_ED", "TECH", "EF"],
    4: ["FR", "MATH", "SCI_OBS", "ECM", "EPS", "DRAW", "MUSIC", "ART_ED", "TECH", "EF", "HIST", "GEO"],
    5: ["FR", "MATH", "SCI_OBS", "ECM", "EPS", "DRAW", "MUSIC", "ART_ED", "TECH", "EF", "HIST", "GEO"],
    6: ["FR", "MATH", "SCI_OBS", "ECM", "EPS", "DRAW", "MUSIC", "ART_ED", "TECH", "EF", "HIST", "GEO"],
}

F2_MAPPING = {
    7: ["FR", "MATH", "ANG", "EPS", "DRAW", "MUSIC", "TECH", "SCI_NAT", "SCI_PHY", "HIST", "GEO", "ACT_RUR"],
    8: ["FR", "MATH", "ANG", "EPS", "DRAW", "MUSIC", "TECH", "EF", "SCI_NAT", "SCI_PHY", "HIST", "GEO", "ACT_RUR"],
    9: ["FR", "MATH", "ANG", "EPS", "DRAW", "MUSIC", "TECH", "SCI_NAT", "SCI_PHY", "HIST", "GEO", "ACT_RUR"],
}


def seed_official_subjects(apps, schema_editor):
    EducationLevel = apps.get_model("pedagogie", "EducationLevel")
    Subject = apps.get_model("pedagogie", "Subject")
    EducationLevelSubject = apps.get_model("pedagogie", "EducationLevelSubject")
    SubjectGroup = apps.get_model("pedagogie", "SubjectGroup")

    subjects = {}
    for code, name in OFFICIAL_SUBJECTS:
        subject, _ = Subject.objects.get_or_create(
            code=code,
            defaults={"name": name, "coefficient": 1, "is_active": True},
        )
        subjects[code] = subject

    # Le référentiel est granulaire : Histoire et Géographie sont deux matières
    # distinctes, même si elles sont souvent portées par un même enseignant.
    for level in EducationLevel.objects.filter(school_type="fundamental_1"):
        year = int(level.name.split()[0].replace("ère", "").replace("ème", ""))
        for order, code in enumerate(F1_MAPPING.get(year, []), 1):
            EducationLevelSubject.objects.get_or_create(
                education_level=level,
                subject=subjects[code],
                defaults={"coefficient": 1, "order": order, "is_active": True},
            )

    for level in EducationLevel.objects.filter(school_type="fundamental_2"):
        year = int(level.name.split()[0].replace("ème", ""))
        for order, code in enumerate(F2_MAPPING.get(year, []), 1):
            EducationLevelSubject.objects.get_or_create(
                education_level=level,
                subject=subjects[code],
                defaults={"coefficient": 1, "order": order, "is_active": True},
            )

    lhg, _ = SubjectGroup.objects.get_or_create(
        code="LHG",
        defaults={"name": "Lettres – Histoire – Géographie", "is_active": True},
    )
    lhg.subjects.set([subjects["FR"], subjects["HIST"], subjects["GEO"]])


def seed_teaching_organization(apps, schema_editor):
    EducationLevel = apps.get_model("pedagogie", "EducationLevel")
    EducationLevel.objects.filter(school_type__in=["preschool", "fundamental_1"]).update(
        teaching_organization="class_based"
    )
    EducationLevel.objects.filter(school_type__in=["fundamental_2", "high_school", "vocational"]).update(
        teaching_organization="subject_based"
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("pedagogie", "0005_pedagogical_catalog"),
    ]

    operations = [
        migrations.AddField(
            model_name="educationlevel",
            name="teaching_organization",
            field=models.CharField(
                choices=[
                    ("class_based", "Organisation centrée sur la classe"),
                    ("subject_based", "Organisation par matière"),
                    ("hybrid", "Organisation mixte"),
                ],
                default="subject_based",
                max_length=20,
                verbose_name="Organisation pédagogique",
            ),
        ),
        migrations.CreateModel(
            name="SubjectGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=30, unique=True, verbose_name="Code")),
                ("name", models.CharField(max_length=100, verbose_name="Groupe")),
                ("is_active", models.BooleanField(default=True, verbose_name="Actif")),
                ("subjects", models.ManyToManyField(blank=True, related_name="groups", to="pedagogie.subject", verbose_name="Matières")),
            ],
            options={
                "ordering": ["name"],
                "verbose_name": "Groupe de matières",
                "verbose_name_plural": "Groupes de matières",
            },
        ),
        migrations.CreateModel(
            name="TeacherSubject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_active", models.BooleanField(default=True, verbose_name="Actif")),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="qualified_teachers", to="pedagogie.subject", verbose_name="Matière")),
                ("teacher", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="qualified_subjects", to="administration.teacher", verbose_name="Enseignant")),
            ],
            options={
                "ordering": ["teacher__user__last_name", "subject__name"],
                "verbose_name": "Matière maîtrisée par l'enseignant",
                "verbose_name_plural": "Matières maîtrisées par les enseignants",
            },
        ),
        migrations.CreateModel(
            name="ClassTeacher",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("classe", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="class_teacher", to="pedagogie.classe", verbose_name="Classe")),
                ("teacher", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="titular_classes", to="administration.teacher", verbose_name="Enseignant")),
            ],
            options={
                "verbose_name": "Enseignant titulaire",
                "verbose_name_plural": "Enseignants titulaires",
            },
        ),
        migrations.AddConstraint(
            model_name="teachersubject",
            constraint=models.UniqueConstraint(fields=("teacher", "subject"), name="unique_teacher_subject_qualification"),
        ),
        migrations.RunPython(seed_official_subjects, noop),
        migrations.RunPython(seed_teaching_organization, noop),
    ]
