from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("administration", "0017_teacherpayment_options"),
    ]

    operations = [
        migrations.CreateModel(
            name="OtherPersonnel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("employee_number", models.CharField(max_length=30, unique=True, verbose_name="Matricule")),
                ("first_name", models.CharField(max_length=100, verbose_name="Prénom(s)")),
                ("last_name", models.CharField(max_length=100, verbose_name="Nom")),
                ("function", models.CharField(max_length=120, verbose_name="Fonction")),
                ("contract_type", models.CharField(choices=[("permanent", "Permanent"), ("contractuel", "Contractuel"), ("vacataire", "Vacataire"), ("temporaire", "Temporaire")], default="permanent", max_length=20, verbose_name="Statut")),
                ("phone", models.CharField(blank=True, max_length=30, verbose_name="Téléphone")),
                ("email", models.EmailField(blank=True, max_length=254, verbose_name="Email")),
                ("address", models.CharField(blank=True, max_length=255, verbose_name="Adresse")),
                ("date_of_birth", models.DateField(blank=True, null=True, verbose_name="Date de naissance")),
                ("hire_date", models.DateField(blank=True, null=True, verbose_name="Date de recrutement / prise de fonction")),
                ("is_active", models.BooleanField(default=True, verbose_name="Actif")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="other_personnel", to="administration.school", verbose_name="Établissement")),
            ],
            options={
                "verbose_name": "Autre membre du personnel",
                "verbose_name_plural": "Autres membres du personnel",
                "ordering": ["last_name", "first_name"],
            },
        ),
    ]
