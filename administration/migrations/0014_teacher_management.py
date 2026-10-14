from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("administration", "0013_remove_schoolyear_unique_active_open_school_year")]

    operations = [
        migrations.AddField(model_name="teacher", name="address", field=models.CharField(blank=True, max_length=255, verbose_name="Adresse")),
        migrations.AddField(model_name="teacher", name="date_of_birth", field=models.DateField(blank=True, null=True, verbose_name="Date de naissance")),
        migrations.AddField(model_name="teacher", name="photo", field=models.ImageField(blank=True, null=True, upload_to="teachers/photos/", verbose_name="Photo")),
        migrations.AddField(model_name="teacher", name="contract_type", field=models.CharField(choices=[("permanent", "Permanent"), ("vacataire", "Vacataire")], default="permanent", max_length=20, verbose_name="Statut")),
        migrations.AddField(model_name="teacher", name="pedagogical_profile", field=models.CharField(blank=True, choices=[("generaliste", "Généraliste"), ("specialiste", "Spécialiste"), ("formateur_metier", "Formateur métier")], default="", max_length=30, verbose_name="Profil pédagogique")),
        migrations.AddField(model_name="teacher", name="monthly_salary", field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name="Salaire mensuel fixe")),
        migrations.AddField(model_name="teacher", name="weekly_obligation", field=models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name="Obligation hebdomadaire (h)")),
        migrations.AddField(model_name="teacher", name="complementary_hours_allowed", field=models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name="Heures complémentaires autorisées (h)")),
        migrations.AddField(model_name="teacher", name="hourly_rate", field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name="Taux horaire")),
        migrations.AddField(model_name="teacher", name="hours_cap", field=models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, verbose_name="Plafond d'heures (h)")),
        migrations.AddField(model_name="teacher", name="contract_start_date", field=models.DateField(blank=True, null=True, verbose_name="Début du contrat")),
        migrations.AddField(model_name="teacher", name="contract_end_date", field=models.DateField(blank=True, null=True, verbose_name="Fin du contrat")),
    ]
