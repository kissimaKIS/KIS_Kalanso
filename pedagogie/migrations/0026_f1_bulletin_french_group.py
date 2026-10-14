from django.db import migrations


def seed(apps, schema_editor):
    EducationLevel = apps.get_model("pedagogie", "EducationLevel")
    Subject = apps.get_model("pedagogie", "Subject")
    EducationLevelSubject = apps.get_model("pedagogie", "EducationLevelSubject")

    french = Subject.objects.filter(code="FR").first()
    if not french:
        return

    for level_code in ("F1-3", "F1-4", "F1-5", "F1-6"):
        level = EducationLevel.objects.filter(code=level_code).first()
        if not level:
            continue
        EducationLevelSubject.objects.update_or_create(
            education_level=level,
            subject=french,
            defaults={
                "weekly_hours": 0,
                "coefficient": 1,
                "role": "secondary",
                "is_required": False,
                "order": 999,
                "is_active": True,
            },
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("pedagogie", "0025_referentiel_centre_professionnel_terrain")]
    operations = [migrations.RunPython(seed, noop)]
