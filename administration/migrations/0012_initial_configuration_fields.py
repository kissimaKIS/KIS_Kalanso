from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("administration", "0011_school_honor_roll_threshold")]

    operations = [
        migrations.AddField(
            model_name="school", name="license_level",
            field=models.CharField(blank=True, choices=[("1", "1 — École fondamentale"), ("2", "2 — Lycée ou Centre professionnel"), ("3", "3 — Lycée et Centre professionnel"), ("4", "4 — Complexe")], default="", max_length=1, verbose_name="Niveau de licence"),
        ),
        migrations.AddField(
            model_name="school", name="ministry_name",
            field=models.CharField(blank=True, max_length=150, verbose_name="Ministère"),
        ),
        migrations.CreateModel(
            name="HonorRollRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("school_type", models.CharField(choices=[("preschool", "Préscolaire"), ("fundamental_1", "Fondamentale 1"), ("fundamental_2", "Fondamentale 2"), ("high_school", "Lycée"), ("vocational", "Centre professionnel")], max_length=30, verbose_name="Contexte pédagogique")),
                ("scale", models.PositiveSmallIntegerField(choices=[(10, "/10"), (20, "/20")], verbose_name="Barème")),
                ("threshold", models.DecimalField(decimal_places=2, max_digits=5, verbose_name="Seuil")),
                ("is_active", models.BooleanField(default=True, verbose_name="Actif")),
                ("school", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="honor_roll_rules", to="administration.school", verbose_name="Établissement")),
            ],
            options={"ordering": ["school_type", "scale"], "verbose_name": "Règle du tableau d'honneur", "verbose_name_plural": "Règles du tableau d'honneur"},
        ),
        migrations.AddConstraint(
            model_name="honorrollrule",
            constraint=models.UniqueConstraint(fields=("school", "school_type", "scale"), name="unique_school_honor_roll_rule"),
        ),
    ]
