from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("pedagogie", "0037_bulletin_configuration")]

    operations = [
        migrations.AddField(
            model_name="evaluation",
            name="nature",
            field=models.CharField(
                choices=[
                    ("punctual", "Évaluation ponctuelle"),
                    ("periodic_composition", "Composition de période"),
                ],
                default="punctual",
                max_length=30,
                verbose_name="Nature",
            ),
        ),
    ]
