from decimal import Decimal
from django.db import migrations, models


SUBJECTS = [
    ("FR", "Français"),
    ("MATH", "Mathématiques"),
    ("PHCH", "Physique - Chimie"),
    ("SVT", "Biologie / SVT"),
    ("HIST", "Histoire"),
    ("GEO", "Géographie"),
    ("HG", "Histoire - Géographie"),
    ("LV1", "Langue Vivante 1"),
    ("LV2", "Langue Vivante 2"),
    ("ECM", "Éducation Civique et Morale"),
    ("LNGNAT", "Langues Nationales"),
    ("EPS", "Éducation Physique et Sportive"),
    ("LITFR", "Littérature / Français"),
    ("PHILO", "Philosophie"),
    ("ECOGESTSOC", "Économie / Gestion / Socio"),
    ("ARTDM", "Arts / Dessin / Musique"),
    ("GENIE", "Génie mécanique / électrique / civil"),
    ("DESSININD", "Dessin Industriel"),
    ("DESSINTECH", "Dessin Technique"),
    ("INITTECH", "Initiation à la Technologie"),
    ("ATELIER", "Atelier / Travaux Pratiques"),
    ("COMPTA", "Comptabilité & Finance"),
    ("ECO_DROIT", "Économie Générale & Droit"),
    ("MATHAPP", "Mathématiques Appliquées"),
    ("ORGINFO", "Organisation / Informatique de gestion"),
    ("ANGCOMM", "Anglais Commercial"),
    ("RMT", "Résistance des Matériaux & Topographie"),
    ("PHBAT", "Physique du Bâtiment"),
    ("ARCHI", "Architecture & Dessin technique"),
    ("PRATPRO", "Pratique Professionnelle (Atelier)"),
    ("TECHSPEC", "Technologie de la Spécialité"),
    ("DESSINEXEC", "Dessin d'Exécution"),
    ("CALCPRO", "Calcul Professionnel (Maths appliquées)"),
    ("CIVISME", "Français / Civisme"),
    ("PROSPEC", "Matières professionnelles"),
    ("EOE", "Économie et Organisation des Entreprises"),
    ("DROIT", "Droit Civil / Commercial / du Travail"),
    ("TEF", "Technique d'Expression (Français)"),
    ("ANGAPP", "Anglais Appliqué"),
    ("MATHFIN", "Mathématiques Financières"),
    ("BUREAU", "Bureautique / Secrétariat"),
    ("INFO_PRAT", "Informatique / Pratique"),
    ("TACHAT", "Techniques de Vente"),
    ("TPIND", "Travaux Pratiques en Atelier"),
    ("HYGIENE", "Hygiène et Sécurité dans l'Atelier"),
    ("MATHSCIPH", "Mathématiques & Sciences Physiques"),
    ("FRANGTECH", "Français / Anglais Technique"),
]

# code, name, school_type, kind, order
TRACKS = [
    ("LY-11-SCI", "11e Sciences", "high_school", "series", 10),
    ("LY-11-L", "11e Lettres", "high_school", "series", 11),
    ("LY-TSE", "Terminale TSE", "high_school", "series", 20),
    ("LY-TSEXP", "Terminale TSExp", "high_school", "series", 21),
    ("LY-TLL", "Terminale TLL", "high_school", "series", 22),
    ("LY-TAL", "Terminale TAL", "high_school", "series", 23),
    ("LY-TSS", "Terminale TSS", "high_school", "series", 24),
    ("LY-TSECO", "Terminale TSEco", "high_school", "series", 25),
    ("LY-10-TECH", "10e Technique", "high_school", "series", 30),
    ("LY-STI", "STI", "high_school", "series", 31),
    ("LY-STG-TE", "STG / TE", "high_school", "series", 32),
    ("LY-TGC", "TGC", "high_school", "series", 33),
    ("BT-TERTIAIRE", "BT Tertiaire", "vocational", "training", 10),
    ("BT-INDUSTRIEL", "BT Industriel", "vocational", "training", 11),
]

# track_code, level_code
TRACK_LEVELS = [
    ("LY-11-SCI", "LYC-11"), ("LY-11-L", "LYC-11"),
    ("LY-TSE", "LYC-12"), ("LY-TSEXP", "LYC-12"), ("LY-TLL", "LYC-12"),
    ("LY-TAL", "LYC-12"), ("LY-TSS", "LYC-12"), ("LY-TSECO", "LYC-12"),
    ("LY-10-TECH", "LYC-10"),
    ("LY-STI", "LYC-11"), ("LY-STI", "LYC-12"),
    ("LY-STG-TE", "LYC-11"), ("LY-STG-TE", "LYC-12"),
    ("LY-TGC", "LYC-11"), ("LY-TGC", "LYC-12"),
    ("BT-TERTIAIRE", "BT-1"), ("BT-TERTIAIRE", "BT-2"),
    ("BT-TERTIAIRE", "BT-3"),
    ("BT-INDUSTRIEL", "BT-1"), ("BT-INDUSTRIEL", "BT-2"),
    ("BT-INDUSTRIEL", "BT-3"),
]

# (track, subject, hours, coefficient, role, required)
PROGRAMS = {
    "LY-10-TECH": [
        ("MATH", 5, 4, "principal"), ("PHCH", 4, 3, "principal"),
        ("DESSINTECH", 4, 3, "principal"), ("FR", 4, 3, "principal"),
        ("INITTECH", 3, 2, "secondary"), ("HG", 2, 2, "secondary"),
        ("LV1", 3, 2, "secondary"), ("ATELIER", 4, 2, "secondary"),
        ("EPS", 2, 1, "common"),
    ],
    "LY-11-SCI": [
        ("MATH", 5, 5, "principal"), ("PHCH", 4, 4, "principal"),
        ("SVT", 3, 3, "principal"), ("FR", 3, 2, "secondary"),
        ("HG", 2, 2, "secondary"), ("LV1", 3, 2, "secondary"),
        ("EPS", 2, 1, "common"),
    ],
    "LY-11-L": [
        ("LITFR", 5, 5, "principal"), ("LV1", 4, 3, "principal"),
        ("LV2", 3, 3, "principal"), ("HG", 3, 3, "principal"),
        ("MATH", 2, 2, "secondary"), ("EPS", 2, 1, "common"),
    ],
    "LY-TSE": [
        ("MATH", 6, 6, "principal"), ("PHCH", 6, 5, "principal"),
        ("LITFR", 3, 2, "secondary"), ("PHILO", 2, 2, "secondary"),
        ("LV1", 3, 2, "secondary"), ("EPS", 2, 1, "common"),
    ],
    "LY-TSEXP": [
        ("MATH", 4, 3, "principal"), ("PHCH", 5, 4, "principal"),
        ("SVT", 4, 4, "principal"), ("LITFR", 3, 2, "secondary"),
        ("PHILO", 2, 2, "secondary"), ("LV1", 3, 2, "secondary"),
        ("EPS", 2, 1, "common"),
    ],
    "LY-TLL": [
        ("MATH", 2, 2, "secondary"), ("LITFR", 5, 5, "principal"),
        ("PHILO", 3, 3, "principal"), ("HG", 3, 2, "secondary"),
        ("LV1", 4, 4, "principal"), ("LV2", 4, 3, "principal"),
        ("EPS", 2, 1, "common"),
    ],
    "LY-TAL": [
        ("MATH", 2, 2, "secondary"), ("LITFR", 5, 5, "principal"),
        ("PHILO", 3, 3, "principal"), ("HG", 3, 2, "secondary"),
        ("LV1", 4, 4, "principal"), ("LV2", 4, 3, "principal"),
        ("ARTDM", 3, 3, "principal"), ("EPS", 2, 1, "common"),
    ],
    "LY-TSS": [
        ("MATH", 3, 2, "secondary"), ("LITFR", 3, 2, "secondary"),
        ("PHILO", 4, 4, "principal"), ("HG", 4, 4, "principal"),
        ("ECOGESTSOC", 3, 3, "principal"), ("LV1", 3, 2, "secondary"),
        ("EPS", 2, 1, "common"),
    ],
    "LY-TSECO": [
        ("MATH", 4, 4, "principal"), ("LITFR", 3, 2, "secondary"),
        ("PHILO", 2, 2, "secondary"), ("HG", 3, 2, "secondary"),
        ("ECOGESTSOC", 5, 5, "principal"), ("LV1", 3, 2, "secondary"),
        ("EPS", 2, 1, "common"),
    ],
    "LY-STI": [
        ("GENIE", 9, 6, "principal"), ("MATH", 6, 5, "principal"),
        ("PHCH", 5, 4, "principal"), ("DESSININD", 4, 3, "secondary"),
        ("FR", 3, 2, "secondary"), ("LV1", 3, 2, "secondary"),
        ("PHILO", 2, 2, "secondary"), ("EPS", 2, 1, "common"),
    ],
    "LY-STG-TE": [
        ("COMPTA", 6, 5, "principal"), ("ECO_DROIT", 4, 4, "principal"),
        ("MATHAPP", 4, 4, "principal"), ("ORGINFO", 4, 3, "secondary"),
        ("FR", 3, 2, "secondary"), ("ANGCOMM", 3, 2, "secondary"),
        ("HG", 2, 2, "secondary"), ("EPS", 2, 1, "common"),
    ],
    "LY-TGC": [
        ("RMT", 8, 5, "principal"), ("MATH", 6, 5, "principal"),
        ("PHBAT", 4, 3, "principal"), ("ARCHI", 5, 3, "secondary"),
        ("FRANGTECH", 3, 2, "secondary"), ("EPS", 2, 1, "common"),
    ],
    "BT-TERTIAIRE": [
        ("PROSPEC", 11, 6, "principal"), ("EOE", 3, 3, "secondary"),
        ("DROIT", 2, 2, "secondary"), ("TEF", 3, 2, "secondary"),
        ("ANGAPP", 3, 2, "secondary"), ("MATHFIN", 3, 3, "secondary"),
        ("INFO_PRAT", 4, 2, "secondary"),
    ],
    "BT-INDUSTRIEL": [
        ("TPIND", 13, 6, "principal"), ("TECHSPEC", 4, 4, "principal"),
        ("DESSININD", 4, 3, "secondary"), ("MATHSCIPH", 4, 3, "secondary"),
        ("HYGIENE", 1, 1, "secondary"), ("FRANGTECH", 2, 1, "secondary"),
    ],
}

# CAP generic program from the supplied reference; intentionally preloaded but
# editable, not presented as an IPN-certified curriculum.
CAP_PROGRAM = [
    ("PRATPRO", 17, 8, "principal"), ("TECHSPEC", 3, 3, "principal"),
    ("DESSINEXEC", 3, 2, "secondary"), ("CALCPRO", 2, 2, "secondary"),
    ("CIVISME", 2, 1, "secondary"),
]


def seed_reference(apps, schema_editor):
    EducationLevel = apps.get_model("pedagogie", "EducationLevel")
    Subject = apps.get_model("pedagogie", "Subject")
    EducationLevelSubject = apps.get_model("pedagogie", "EducationLevelSubject")
    PedagogicalTrack = apps.get_model("pedagogie", "PedagogicalTrack")
    TrackLevel = apps.get_model("pedagogie", "TrackLevel")
    TrackLevelSubject = apps.get_model("pedagogie", "TrackLevelSubject")

    # Terminale is the pedagogical label used by the supplied reference.
    EducationLevel.objects.filter(code="LYC-12").update(name="Terminale")
    EducationLevel.objects.get_or_create(
        code="BT-3",
        defaults={
            "name": "BT 3", "school_type": "vocational", "order": 5,
            "is_exam_level": True, "exam_name": "BT3", "allows_free_candidate": True,
            "teaching_organization": "subject_based", "is_active": True,
        },
    )

    subjects = {}
    for code, name in SUBJECTS:
        obj, _ = Subject.objects.get_or_create(code=code, defaults={"name": name, "coefficient": 1, "is_active": True})
        subjects[code] = obj

    # 10e general: one generic curriculum, all subjects required in the supplied reference.
    ten = EducationLevel.objects.get(code="LYC-10")
    ten_program = [
        ("FR", 5, 4, "principal"), ("MATH", 4, 4, "principal"),
        ("PHCH", 3, 3, "principal"), ("SVT", 2, 2, "secondary"),
        ("HG", 3, 2, "secondary"), ("LV1", 3, 2, "secondary"),
        ("ECM", 1, 1, "secondary"), ("LNGNAT", 1, 1, "secondary"),
        ("EPS", 2, 1, "common"),
    ]
    for order, (code, hours, coeff, role) in enumerate(ten_program, 1):
        EducationLevelSubject.objects.update_or_create(
            education_level=ten, subject=subjects[code],
            defaults={"weekly_hours": Decimal(str(hours)), "coefficient": coeff, "role": role, "is_required": True, "order": order, "is_active": True},
        )

    tracks = {}
    for code, name, school_type, kind, order in TRACKS:
        track, _ = PedagogicalTrack.objects.get_or_create(
            code=code,
            defaults={"name": name, "school_type": school_type, "kind": kind, "order": order, "is_active": True},
        )
        tracks[code] = track

    for track_code, level_code in TRACK_LEVELS:
        level = EducationLevel.objects.get(code=level_code)
        TrackLevel.objects.get_or_create(
            track=tracks[track_code], education_level=level,
            defaults={"order": level.order, "is_active": True},
        )

    for track_code, program in PROGRAMS.items():
        track = tracks[track_code]
        for level in TrackLevel.objects.filter(track=track, is_active=True):
            for order, (code, hours, coeff, role) in enumerate(program, 1):
                TrackLevelSubject.objects.update_or_create(
                    track_level=level, subject=subjects[code],
                    defaults={"weekly_hours": Decimal(str(hours)), "coefficient": coeff, "role": role, "is_required": True, "order": order, "is_active": True},
                )

    # CAP 1 and CAP 2 use the supplied generic CAP program.
    for level in EducationLevel.objects.filter(code__in=["CAP-1", "CAP-2"]):
        for order, (code, hours, coeff, role) in enumerate(CAP_PROGRAM, 1):
            EducationLevelSubject.objects.update_or_create(
                education_level=level, subject=subjects[code],
                defaults={"weekly_hours": Decimal(str(hours)), "coefficient": coeff, "role": role, "is_required": True, "order": order, "is_active": True},
            )


def reverse_reference(apps, schema_editor):
    # Data is a reference preload. We intentionally do not delete administrator
    # data on reverse migration.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("pedagogie", "0011_normalize_catalog"),
    ]

    operations = [
        migrations.AddField(
            model_name="educationlevelsubject",
            name="weekly_hours",
            field=models.DecimalField(decimal_places=1, default=0, max_digits=4, verbose_name="Volume horaire / semaine"),
        ),
        migrations.AddField(
            model_name="educationlevelsubject",
            name="role",
            field=models.CharField(choices=[("principal", "Principale"), ("secondary", "Secondaire"), ("common", "Commune")], default="secondary", max_length=20, verbose_name="Statut pédagogique"),
        ),
        migrations.AddField(
            model_name="educationlevelsubject",
            name="is_required",
            field=models.BooleanField(default=True, verbose_name="Obligatoire"),
        ),
        migrations.AddField(
            model_name="tracklevelsubject",
            name="weekly_hours",
            field=models.DecimalField(decimal_places=1, default=0, max_digits=4, verbose_name="Volume horaire / semaine"),
        ),
        migrations.AddField(
            model_name="tracklevelsubject",
            name="role",
            field=models.CharField(choices=[("principal", "Principale"), ("secondary", "Secondaire"), ("common", "Commune")], default="secondary", max_length=20, verbose_name="Statut pédagogique"),
        ),
        migrations.AddField(
            model_name="tracklevelsubject",
            name="is_required",
            field=models.BooleanField(default=True, verbose_name="Obligatoire"),
        ),
        migrations.RunPython(seed_reference, reverse_reference),
    ]
