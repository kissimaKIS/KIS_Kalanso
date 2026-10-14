from django.db import migrations, models


def activate_existing_primary_types(apps, schema_editor):
    School = apps.get_model("administration", "School")
    SchoolTypeActivation = apps.get_model("administration", "SchoolTypeActivation")
    rows = [
        SchoolTypeActivation(school_id=school.pk, school_type=school.school_type, is_active=True)
        for school in School.objects.all().only("pk", "school_type")
    ]
    if rows:
        SchoolTypeActivation.objects.bulk_create(rows, ignore_conflicts=True)


def remove_activations(apps, schema_editor):
    SchoolTypeActivation = apps.get_model("administration", "SchoolTypeActivation")
    SchoolTypeActivation.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("administration", "0004_school_type_and_schoolyear_school"),
    ]

    operations = [
        migrations.CreateModel(
            name="SchoolTypeActivation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("school_type", models.CharField(choices=[
                    ("preschool", "Préscolaire"),
                    ("fundamental_1", "Fondamentale 1"),
                    ("fundamental_2", "Fondamentale 2"),
                    ("high_school", "Lycée"),
                    ("vocational", "Centre professionnel"),
                ], max_length=30, verbose_name="Type d'enseignement")),
                ("is_active", models.BooleanField(default=True, verbose_name="Actif")),
                ("activated_at", models.DateTimeField(auto_now_add=True)),
                ("school", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="type_activations", to="administration.school", verbose_name="Établissement")),
            ],
            options={
                "verbose_name": "Type d'enseignement activé",
                "verbose_name_plural": "Types d'enseignement activés",
                "ordering": ["school_type"],
            },
        ),
        migrations.AddConstraint(
            model_name="schooltypeactivation",
            constraint=models.UniqueConstraint(fields=("school", "school_type"), name="unique_school_school_type_activation"),
        ),
        migrations.AlterField(
            model_name="school",
            name="school_type",
            field=models.CharField(choices=[
                ("preschool", "Préscolaire"),
                ("fundamental_1", "Fondamentale 1"),
                ("fundamental_2", "Fondamentale 2"),
                ("high_school", "Lycée"),
                ("vocational", "Centre professionnel"),
            ], max_length=30, verbose_name="Type principal"),
        ),
        migrations.RunPython(activate_existing_primary_types, remove_activations),
    ]
