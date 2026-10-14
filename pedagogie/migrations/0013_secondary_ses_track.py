from decimal import Decimal
from django.db import migrations, models


def seed_ses(apps, schema_editor):
    PedagogicalTrack = apps.get_model("pedagogie", "PedagogicalTrack")
    EducationLevel = apps.get_model("pedagogie", "EducationLevel")
    Subject = apps.get_model("pedagogie", "Subject")
    TrackLevel = apps.get_model("pedagogie", "TrackLevel")
    TrackLevelSubject = apps.get_model("pedagogie", "TrackLevelSubject")

    level = EducationLevel.objects.get(code="LYC-11")
    track, _ = PedagogicalTrack.objects.get_or_create(
        code="LY-11-SES",
        defaults={
            "name": "11e Sciences Économiques et Sociales (11e SES)",
            "school_type": "high_school",
            "kind": "series",
            "order": 12,
            "is_active": True,
        },
    )
    track_level, _ = TrackLevel.objects.get_or_create(
        track=track, education_level=level,
        defaults={"order": 12, "is_active": True},
    )

    subjects = {}
    definitions = [
        ("ECOSOC", "Économie & Sociologie"),
        ("MATH", "Mathématiques"),
        ("FR", "Français"),
        ("HG", "Histoire - Géographie"),
        ("LV1", "Langue Vivante 1"),
        ("PHCH", "Physique - Chimie"),
        ("SVT", "Biologie / SVT"),
        ("ECM", "Éducation Civique et Morale"),
        ("EPS", "Éducation Physique et Sportive"),
    ]
    for code, name in definitions:
        subject, _ = Subject.objects.get_or_create(
            code=code, defaults={"name": name, "coefficient": 1, "is_active": True}
        )
        subjects[code] = subject

    program = [
        ("ECOSOC", 4, None, 4, "principal"),
        ("MATH", 3, 4, 3, "principal"),
        ("FR", 3, None, 2, "secondary"),
        ("HG", 3, None, 2, "secondary"),
        ("LV1", 3, None, 2, "secondary"),
        ("PHCH", 2, None, 2, "secondary"),
        ("ECM", 1, None, 1, "secondary"),
        ("EPS", 2, None, 1, "common"),
    ]
    for order, (code, hours_min, hours_max, coeff, role) in enumerate(program, 1):
        TrackLevelSubject.objects.update_or_create(
            track_level=track_level, subject=subjects[code],
            defaults={
                "weekly_hours": Decimal(str(hours_min)),
                "weekly_hours_max": Decimal(str(hours_max)) if hours_max is not None else None,
                "coefficient": coeff, "role": role, "is_required": True,
                "order": order, "is_active": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("pedagogie", "0012_initial_secondary_referential")]

    operations = [
        migrations.AddField(
            model_name="tracklevelsubject",
            name="weekly_hours_max",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True, verbose_name="Volume horaire / semaine (max)"),
        ),
        migrations.RunPython(seed_ses, migrations.RunPython.noop),
    ]
