from django.db import migrations, models
from django.core.validators import MaxValueValidator, MinValueValidator


class Migration(migrations.Migration):

    dependencies = [
        ("pedagogie", "0018_bulletin"),
    ]

    operations = [
        migrations.AlterField(
            model_name="grade",
            name="class_average",
            field=models.FloatField(
                blank=True,
                null=True,
                validators=[MinValueValidator(0), MaxValueValidator(20)],
                verbose_name="Moyenne de classe (A)",
            ),
        ),
        migrations.AlterField(
            model_name="grade",
            name="composition",
            field=models.FloatField(
                blank=True,
                null=True,
                validators=[MinValueValidator(0), MaxValueValidator(20)],
                verbose_name="Composition (B)",
            ),
        ),
        migrations.AlterField(
            model_name="grade",
            name="devoir",
            field=models.FloatField(
                blank=True,
                null=True,
                validators=[MinValueValidator(0), MaxValueValidator(20)],
                verbose_name="Devoir (suivi)",
            ),
        ),
    ]
