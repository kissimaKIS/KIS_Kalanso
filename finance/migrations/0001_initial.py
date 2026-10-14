from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [("pedagogie","0001_initial")]
    operations = [
        migrations.CreateModel(
            name="FeeType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, verbose_name="Type de frais")),
                ("amount", models.DecimalField(decimal_places=0, max_digits=10, verbose_name="Montant")),
                ("is_required", models.BooleanField(default=False, verbose_name="Frais obligatoire")),
                ("is_active", models.BooleanField(default=True, verbose_name="Actif")),
                ("classe", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fee_types", to="pedagogie.classe")),
                ("school_year", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fee_types", to="administration.schoolyear")),
            ],
            options={"ordering":["name"],"verbose_name":"Type de frais","verbose_name_plural":"Types de frais"},
        ),
        migrations.CreateModel(
            name="Invoice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("total_amount", models.DecimalField(decimal_places=0, max_digits=10, verbose_name="Montant total")),
                ("paid_amount", models.DecimalField(decimal_places=0, default=0, max_digits=10, verbose_name="Montant payé")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("enrollment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="invoices", to="pedagogie.enrollment")),
                ("fee_type", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="invoices", to="finance.feetype")),
            ],
            options={"verbose_name":"Facture","verbose_name_plural":"Factures"},
        ),
        migrations.CreateModel(
            name="Payment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=0, max_digits=10, verbose_name="Montant payé")),
                ("date", models.DateField(auto_now_add=True)),
                ("receipt_number", models.CharField(blank=True, max_length=30, unique=True)),
                ("comment", models.TextField(blank=True, null=True)),
                ("invoice", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payments", to="finance.invoice")),
            ],
            options={"ordering":["-date","-id"],"verbose_name":"Paiement","verbose_name_plural":"Paiements"},
        ),
        migrations.CreateModel(
            name="StudentOption",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("start_date", models.DateField(auto_now_add=True)),
                ("end_date", models.DateField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("enrollment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="options", to="pedagogie.enrollment")),
                ("fee_type", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="student_options", to="finance.feetype")),
            ],
            options={"verbose_name":"Option élève","verbose_name_plural":"Options élèves"},
        ),
        migrations.AddConstraint(model_name="studentoption", constraint=models.UniqueConstraint(fields=("enrollment","fee_type"), name="unique_student_option")),
    ]
