from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("pedagogie", "0026_f1_bulletin_french_group")]

    operations = [
        migrations.CreateModel(
            name="PassageDecision",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("PREPARATION", "Préparation"), ("CAP_DECIDED", "Décision du CAP"), ("DIRECTOR_VALIDATED", "Validée par le Directeur")], default="PREPARATION", max_length=24, verbose_name="État")),
                ("cap_decided_at", models.DateTimeField(blank=True, null=True, verbose_name="Décision du CAP le")),
                ("director_validated_at", models.DateTimeField(blank=True, null=True, verbose_name="Validée par le Directeur le")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("classe", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="passage_decisions", to="pedagogie.classe", verbose_name="Classe")),
                ("cap_decided_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="cap_decisions_entered", to="administration.user", verbose_name="Décision du CAP saisie par")),
                ("director_validated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="validated_passage_decisions", to="administration.user", verbose_name="Validée par le Directeur")),
                ("source_year", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="passage_decisions", to="administration.schoolyear", verbose_name="Année scolaire")),
            ],
            options={"ordering": ["classe__education_level__order", "classe__group", "classe__name"], "verbose_name": "Décision de passage", "verbose_name_plural": "Décisions de passage"},
        ),
        migrations.CreateModel(
            name="PassageDecisionLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("proposal_decision", models.CharField(choices=[("PENDING", "À décider"), ("PASSANT", "Passant"), ("REDOUBLANT", "Redoublant"), ("EXCLU", "Exclu")], default="PENDING", max_length=12, verbose_name="Proposition du conseil")),
                ("cap_decision", models.CharField(choices=[("PENDING", "À décider"), ("PASSANT", "Passant"), ("REDOUBLANT", "Redoublant"), ("EXCLU", "Exclu")], default="PENDING", max_length=12, verbose_name="Décision du CAP")),
                ("director_decision", models.CharField(choices=[("PENDING", "À décider"), ("PASSANT", "Passant"), ("REDOUBLANT", "Redoublant"), ("EXCLU", "Exclu")], default="PENDING", max_length=12, verbose_name="Décision du Directeur")),
                ("observation", models.CharField(blank=True, max_length=255, verbose_name="Observation")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("enrollment", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="passage_decision_line", to="pedagogie.enrollment", verbose_name="Inscription")),
                ("passage", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="pedagogie.passagedecision", verbose_name="Proposition")),
            ],
            options={"ordering": ["enrollment__student__last_name", "enrollment__student__first_name"], "verbose_name": "Ligne de décision de passage", "verbose_name_plural": "Lignes de décision de passage"},
        ),
        migrations.AddConstraint(
            model_name="passagedecision",
            constraint=models.UniqueConstraint(fields=("source_year", "classe"), name="unique_passage_decision_class_year"),
        ),
        migrations.AddConstraint(
            model_name="passagedecisionline",
            constraint=models.UniqueConstraint(fields=("passage", "enrollment"), name="unique_passage_line_enrollment"),
        ),
    ]
