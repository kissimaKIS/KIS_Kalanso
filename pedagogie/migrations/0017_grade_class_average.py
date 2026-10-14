from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedagogie", "0016_transition_target_definition"),
    ]

    operations = [
        migrations.AddField(
            model_name="grade",
            name="class_average",
            field=models.FloatField(
                blank=True,
                null=True,
                validators=[],
                verbose_name="Moyenne de classe (A)",
            ),
        ),
        migrations.AlterField(
            model_name="grade",
            name="devoir",
            field=models.FloatField(
                blank=True,
                null=True,
                validators=[],
                verbose_name="Devoir (suivi)",
            ),
        ),
        migrations.AlterField(
            model_name="grade",
            name="composition",
            field=models.FloatField(
                blank=True,
                null=True,
                validators=[],
                verbose_name="Composition (B)",
            ),
        ),
    ]
