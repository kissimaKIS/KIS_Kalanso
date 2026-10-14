from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("administration", "0020_alter_otherpersonnelpayment_paid_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="school",
            name="honor_roll_threshold",
            field=models.DecimalField(
                decimal_places=2,
                default=14,
                help_text="Champ historique de compatibilité. Les seuils actuels sont réglés séparément par secteur et par barème, sans conversion.",
                max_digits=5,
                verbose_name="Seuil du tableau d’honneur",
            ),
        ),
    ]
