from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("administration", "0018_otherpersonnel")]

    operations = [
        migrations.CreateModel(
            name="OtherPersonnelPayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("period", models.CharField(max_length=30, verbose_name="Période")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, verbose_name="Montant payé")),
                ("paid_at", models.DateField(verbose_name="Date de paiement")),
                ("note", models.CharField(blank=True, max_length=255, verbose_name="Observation")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("personnel", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payments", to="administration.otherpersonnel", verbose_name="Personnel")),
                ("school_year", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="other_personnel_payments", to="administration.schoolyear", verbose_name="Année scolaire")),
            ],
            options={"ordering": ["-paid_at", "personnel__last_name", "personnel__first_name"], "verbose_name": "Paiement autre personnel", "verbose_name_plural": "Paiements autre personnel"},
        ),
        migrations.AddConstraint(
            model_name="otherpersonnelpayment",
            constraint=models.UniqueConstraint(fields=("personnel", "school_year", "period"), name="unique_other_personnel_payment_period"),
        ),
    ]
