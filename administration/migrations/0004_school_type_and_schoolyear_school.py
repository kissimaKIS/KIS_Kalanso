from django.db import migrations, models
import django.db.models.deletion


def migrate_school_types(apps, schema_editor):
    School = apps.get_model("administration", "School")
    SchoolYear = apps.get_model("administration", "SchoolYear")

    # Anciennes valeurs présentes dans les premières versions du MVP.
    School.objects.filter(school_type="fundamental").update(school_type="fundamental_1")
    School.objects.filter(school_type="training_center").update(school_type="vocational")

    schools = list(School.objects.order_by("id"))
    years = SchoolYear.objects.filter(school__isnull=True)
    if years.exists() and schools:
        default_school = next((s for s in schools if s.is_active), schools[0])
        years.update(school_id=default_school.id)


def reverse_school_types(apps, schema_editor):
    School = apps.get_model("administration", "School")
    School.objects.filter(school_type="fundamental_1").update(school_type="fundamental")
    School.objects.filter(school_type="fundamental_2").update(school_type="fundamental")
    School.objects.filter(school_type="vocational").update(school_type="training_center")


class Migration(migrations.Migration):
    dependencies = [("administration", "0003_alter_user_options_alter_school_created_at_and_more")]

    operations = [
        migrations.AddField(
            model_name="schoolyear",
            name="school",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="school_years",
                to="administration.school",
                verbose_name="Établissement",
            ),
        ),
        migrations.RunPython(migrate_school_types, reverse_school_types),
        migrations.AlterField(
            model_name="school",
            name="school_type",
            field=models.CharField(
                choices=[
                    ("preschool", "Préscolaire"),
                    ("fundamental_1", "Fondamentale 1"),
                    ("fundamental_2", "Fondamentale 2"),
                    ("high_school", "Lycée"),
                    ("vocational", "Centre professionnel"),
                ],
                max_length=30,
                verbose_name="Type d'établissement",
            ),
        ),
        migrations.AlterField(
            model_name="schoolyear",
            name="name",
            field=models.CharField(editable=False, max_length=20, verbose_name="Année scolaire"),
        ),
        migrations.AlterField(
            model_name="schoolyear",
            name="school",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="school_years",
                to="administration.school",
                verbose_name="Établissement",
            ),
        ),
        migrations.AddConstraint(
            model_name="schoolyear",
            constraint=models.UniqueConstraint(fields=("school", "name"), name="unique_school_year_name"),
        ),
    ]
