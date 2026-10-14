from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("pedagogie", "0019_alter_grade_class_average_alter_grade_composition_and_more")]

    operations = [
        migrations.AddField(
            model_name="student",
            name="status",
            field=models.CharField(
                choices=[("active", "Élève actif"), ("inactive", "Élève inactif")],
                default="active",
                max_length=10,
                verbose_name="Statut",
            ),
        ),
        migrations.AddField(
            model_name="student",
            name="inactive_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("alumni", "Ancien élève"),
                    ("transferred", "Transféré"),
                    ("removed", "Radié"),
                ],
                max_length=20,
                null=True,
                verbose_name="Motif d'inactivité",
            ),
        ),
    ]
