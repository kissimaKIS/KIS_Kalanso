from django.db import migrations, models


def migrate_fee_categories(apps, schema_editor):
    FeeType = apps.get_model("finance", "FeeType")
    for fee in FeeType.objects.all():
        normalized = (fee.name or "").strip().lower()
        if "réinscription" in normalized or "reinscription" in normalized:
            category = "reenrollment"
        elif "inscription" in normalized:
            category = "registration"
        elif any(token in normalized for token in ("cantine", "transport", "rattrapage", "langue", "informatique", "activité", "activite")):
            category = "optional"
        else:
            category = "tuition"
        fee.category = category
        fee.registration_scope = fee.billing_frequency or "annual"
        if category != "registration":
            fee.cycle_key = ""
        fee.save(update_fields=["category", "registration_scope", "cycle_key"])


def reverse_fee_categories(apps, schema_editor):
    FeeType = apps.get_model("finance", "FeeType")
    for fee in FeeType.objects.all():
        fee.billing_frequency = fee.registration_scope or "annual"
        fee.save(update_fields=["billing_frequency"])


class Migration(migrations.Migration):
    dependencies = [("finance", "0003_fee_type_billing_frequency")]

    operations = [
        migrations.AddField(
            model_name="feetype",
            name="category",
            field=models.CharField(
                choices=[
                    ("registration", "Frais d'inscription"),
                    ("reenrollment", "Frais de réinscription"),
                    ("tuition", "Frais de scolarité"),
                    ("optional", "Frais optionnel"),
                ],
                default="tuition",
                max_length=20,
                verbose_name="Catégorie",
            ),
        ),
        migrations.AddField(
            model_name="feetype",
            name="registration_scope",
            field=models.CharField(
                choices=[("annual", "Année scolaire"), ("cycle", "Cycle")],
                default="annual",
                max_length=10,
                verbose_name="Validité des frais d'inscription",
            ),
        ),
        migrations.AddField(
            model_name="feetype",
            name="cycle_key",
            field=models.CharField(
                blank=True,
                help_text="Identifiant libre permettant à l'établissement de regrouper les années d'un même cycle.",
                max_length=50,
                verbose_name="Cycle financier",
            ),
        ),
        migrations.RunPython(migrate_fee_categories, reverse_fee_categories),
        migrations.RemoveField(model_name="feetype", name="billing_frequency"),
    ]
