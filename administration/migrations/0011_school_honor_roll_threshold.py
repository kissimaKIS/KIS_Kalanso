from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("administration", "0010_merge_0009_schoolyear_and_userroleassignment"),
    ]

    operations = [
        migrations.AddField(
            model_name="school",
            name="honor_roll_threshold",
            field=models.DecimalField(
                decimal_places=2,
                default=14,
                help_text="Moyenne minimale sur 20. En Fondamentale 1, KIS convertit automatiquement la moyenne sur 10.",
                max_digits=5,
                verbose_name="Seuil du tableau d’honneur",
            ),
        ),
    ]
