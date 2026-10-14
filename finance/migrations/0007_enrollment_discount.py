from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("finance", "0006_finance_labels")]

    operations = [
        migrations.CreateModel(
            name="EnrollmentDiscount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("discount_type", models.CharField(choices=[("fixed", "Montant fixe"), ("percentage", "Pourcentage")], max_length=12)),
                ("value", models.DecimalField(decimal_places=2, max_digits=10)),
                ("amount", models.DecimalField(decimal_places=0, max_digits=10, verbose_name="Montant de la remise")),
                ("reason", models.CharField(max_length=150, verbose_name="Motif")),
                ("note", models.TextField(blank=True, verbose_name="Observation")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("enrollment", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="discount", to="pedagogie.enrollment")),
            ],
            options={"verbose_name": "Remise", "verbose_name_plural": "Remises"},
        ),
        migrations.CreateModel(
            name="DiscountAllocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("original_amount", models.DecimalField(decimal_places=0, max_digits=10)),
                ("discount_amount", models.DecimalField(decimal_places=0, max_digits=10)),
                ("discount", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="allocations", to="finance.enrollmentdiscount")),
                ("invoice", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="discount_allocation", to="finance.invoice")),
            ],
            options={"verbose_name": "Affectation de remise", "verbose_name_plural": "Affectations de remise"},
        ),
    ]
