from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("pedagogie", "0014_add_educationlevelsubject_weekly_hours_max"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SchoolYearTransition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("DRAFT", "Préparation"), ("VALIDATED", "Décisions validées"), ("APPLIED", "Inscriptions préparées")], default="DRAFT", max_length=12, verbose_name="État")),
                ("validated_at", models.DateTimeField(blank=True, null=True, verbose_name="Décisions validées le")),
                ("applied_at", models.DateTimeField(blank=True, null=True, verbose_name="Inscriptions préparées le")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("applied_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="applied_transitions", to=settings.AUTH_USER_MODEL, verbose_name="Inscriptions préparées par")),
                ("source_year", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="outgoing_transitions", to="administration.schoolyear", verbose_name="Année source")),
                ("target_year", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="incoming_transitions", to="administration.schoolyear", verbose_name="Année cible")),
                ("validated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="validated_transitions", to=settings.AUTH_USER_MODEL, verbose_name="Décisions validées par")),
            ],
            options={"verbose_name": "Passage d'année", "verbose_name_plural": "Passages d'année", "ordering": ["-source_year__start_date"]},
        ),
        migrations.CreateModel(
            name="PromotionProposal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("student_type", models.CharField(choices=[("regulier", "Régulier"), ("cl", "Candidat libre")], default="regulier", max_length=10, verbose_name="Type d'inscription cible")),
                ("decision", models.CharField(choices=[("PENDING", "À traiter"), ("ACCEPTED", "Acceptée"), ("REJECTED", "Refusée")], default="PENDING", max_length=10, verbose_name="Décision")),
                ("note", models.TextField(blank=True, verbose_name="Observation")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("proposed_classe", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="incoming_proposals", to="pedagogie.classe", verbose_name="Classe proposée")),
                ("source_enrollment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="promotion_proposals", to="pedagogie.enrollment", verbose_name="Inscription source")),
                ("transition", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="proposals", to="pedagogie.schoolyeartransition", verbose_name="Passage")),
            ],
            options={"verbose_name": "Proposition de passage", "verbose_name_plural": "Propositions de passage", "ordering": ["source_enrollment__student__last_name", "source_enrollment__student__first_name"]},
        ),
        migrations.AddConstraint(
            model_name="schoolyeartransition",
            constraint=models.UniqueConstraint(fields=("source_year", "target_year"), name="unique_school_year_transition"),
        ),
        migrations.AddConstraint(
            model_name="promotionproposal",
            constraint=models.UniqueConstraint(fields=("transition", "source_enrollment"), name="unique_transition_source_enrollment"),
        ),
    ]
