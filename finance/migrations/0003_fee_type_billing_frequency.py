from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("finance", "0002_constraints")]

    operations = [
        migrations.AddField(
            model_name="feetype",
            name="billing_frequency",
            field=models.CharField(
                choices=[
                    ("annual", "À chaque inscription annuelle"),
                    ("cycle", "Une seule fois sur le cycle"),
                ],
                default="annual",
                max_length=10,
                verbose_name="Fréquence d'application",
            ),
        ),
    ]
