from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("finance", "0008_feetype_education_level")]

    operations = [
        migrations.AddField(
            model_name="feetype",
            name="school_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("preschool", "Préscolaire"),
                    ("fundamental_1", "Fondamentale 1"),
                    ("fundamental_2", "Fondamentale 2"),
                    ("high_school", "Lycée"),
                    ("vocational", "Centre professionnel"),
                ],
                max_length=30,
                null=True,
                verbose_name="Secteur pédagogique (facultatif)",
            ),
        ),
    ]
