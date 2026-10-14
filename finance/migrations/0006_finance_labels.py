from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0005_feetype_classe_optional"),
    ]

    operations = [
        migrations.AlterField(
            model_name="feetype",
            name="is_required",
            field=models.BooleanField(default=False, verbose_name="Appliquer automatiquement à l'inscription"),
        ),
        migrations.AlterField(
            model_name="feetype",
            name="cycle_key",
            field=models.CharField(
                blank=True,
                help_text="Référence libre pour reconnaître un même cycle d'inscription sur plusieurs années.",
                max_length=50,
                verbose_name="Référence du cycle d'inscription",
            ),
        ),
    ]
