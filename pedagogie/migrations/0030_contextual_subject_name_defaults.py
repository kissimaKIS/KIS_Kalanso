from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pedagogie", "0029_referentiel_secondaire_terrain"),
    ]

    operations = [
        migrations.AlterField(
            model_name="educationlevelsubject",
            name="name",
            field=models.CharField(
                blank=True,
                default="",
                max_length=100,
                verbose_name="Nom",
            ),
        ),
        migrations.AlterField(
            model_name="tracklevelsubject",
            name="name",
            field=models.CharField(
                blank=True,
                default="",
                max_length=100,
                verbose_name="Nom",
            ),
        ),
    ]
